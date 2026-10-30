"""Basket lines from accepted evaluations; confirm; merchant review and in-person edits."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BasketLine, Offer, Product, Session, SessionState
from app.engine.basket import recheck_lines
from app.engine.types import LinePrice
from app.schemas.common import AppError
from app.schemas.events import BasketEvent, DealRequestEvent
from app.schemas.merchant import BasketEditLine, MerchantBasket, ReviewAction
from app.schemas.public import BasketPublic
from app.services import catalog, sessions, trace, views
from app.services.hub import Hubs

S = SessionState


async def _push(db: AsyncSession, hubs: Hubs, session_id: uuid.UUID, action: str, **extra) -> BasketPublic:
    """Tell the customer the new basket and the merchant trace the same change."""
    public = await views.public_basket(db, session_id)
    await hubs.customer.send(session_id, BasketEvent(lines=public.lines, total=public.total))
    await trace.push_basket(
        hubs.merchant, session_id, action, await views.merchant_basket(db, session_id), **extra
    )
    return public


async def _live_by_product(db: AsyncSession, session_id: uuid.UUID) -> dict[str, BasketLine]:
    return {line.product_id: line for line, _ in await views.live_lines(db, session_id)}


async def add_from_evaluation(
    db: AsyncSession, hubs: Hubs, session_id: uuid.UUID, evaluation_id: uuid.UUID
) -> BasketPublic:
    """Only accepted evaluations enter the basket; one line per product (a new one replaces the old).
    Idempotent per evaluation."""
    session = await sessions.get_session(db, session_id)
    sessions.require_state(session, S.intro, S.discovery, S.negotiating)
    offer = await db.get(Offer, evaluation_id)
    if offer is None or offer.session_id != session_id:
        raise AppError("EVALUATION_NOT_FOUND", "Unknown evaluation for this session", 404)
    if offer.decision != "accept":
        raise AppError("EVALUATION_NOT_ACCEPTED", "Only an accepted offer can go in the basket", 409)
    live = await _live_by_product(db, session_id)
    if offer.line_prices and all(
        (line := live.get(lp["product_id"])) is not None and line.offer_id == offer.id
        for lp in offer.line_prices
    ):
        return await views.public_basket(db, session_id)

    lines = [LinePrice(lp["product_id"], lp["qty"], Decimal(lp["line_total"])) for lp in offer.line_prices]
    products = await catalog.product_terms(db, [lp.product_id for lp in lines])
    if len(recheck_lines(products, lines)) != len(lines):
        raise AppError("LINE_INVALID", "That offer is no longer valid (stock or price changed)", 409)

    now = datetime.now(UTC)
    for lp in lines:
        if old := live.get(lp.product_id):
            old.removed_at = now
        db.add(
            BasketLine(
                session_id=session_id,
                offer_id=offer.id,
                product_id=lp.product_id,
                qty=lp.qty,
                line_total=lp.line_total,
            )
        )
    await db.commit()
    await sessions.ensure_negotiating(db, hubs, session)
    return await _push(db, hubs, session_id, "add", evaluation_id=str(offer.id))


async def remove(db: AsyncSession, hubs: Hubs, session_id: uuid.UUID, product_id: str) -> BasketPublic:
    session = await sessions.get_session(db, session_id)
    sessions.require_state(session, S.intro, S.discovery, S.negotiating)
    line = (await _live_by_product(db, session_id)).get(product_id)
    if line is not None:
        line.removed_at = datetime.now(UTC)
        await db.commit()
        return await _push(db, hubs, session_id, "remove", product_id=product_id)
    return await views.public_basket(db, session_id)


async def confirm(db: AsyncSession, hubs: Hubs, session_id: uuid.UUID) -> tuple[Session, BasketPublic]:
    """Confirm & send: re-check every line, then hand the basket to the merchant. Idempotent."""
    session = await sessions.get_session(db, session_id)
    if session.state is S.pending_merchant:
        return session, await views.public_basket(db, session_id)
    sessions.require_state(session, S.negotiating)
    live = await views.live_lines(db, session_id)
    if not live:
        raise AppError("BASKET_EMPTY", "Add something to your basket first", 400)

    lines = [LinePrice(line.product_id, line.qty, line.line_total) for line, _ in live]
    products = await catalog.product_terms(db, [ln.product_id for ln in lines])
    still_valid = {ln.product_id for ln in recheck_lines(products, lines)}
    dropped = [(line, p) for line, p in live if line.product_id not in still_valid]
    if dropped:
        now = datetime.now(UTC)
        for line, _ in dropped:
            line.removed_at = now
        await db.commit()
        await _push(db, hubs, session_id, "dropped", product_ids=[p.product_id for _, p in dropped])
        names = ", ".join(p.product_name for _, p in dropped)
        raise AppError("LINE_INVALID", f"No longer available at that price: {names}. It was removed.", 409)

    session = await sessions.transition(db, hubs, session_id, S.pending_merchant)
    await hubs.merchant.broadcast(
        DealRequestEvent(session_id=session_id, basket=await views.merchant_basket(db, session_id))
    )
    return session, await views.public_basket(db, session_id)


async def review(db: AsyncSession, hubs: Hubs, session_id: uuid.UUID, action: ReviewAction) -> Session:
    """Merchant decision on the deal request (docs/architecture.md#deal-review)."""
    session = await sessions.get_session(db, session_id)
    if action in (ReviewAction.renegotiate_hermion, ReviewAction.renegotiate_in_person):
        sessions.require_state(session, S.pending_merchant)
        target = S.briefing if action is ReviewAction.renegotiate_hermion else S.in_person
        return await sessions.transition(db, hubs, session_id, target)
    sessions.require_state(session, S.pending_merchant, S.in_person)
    if action is ReviewAction.decline:
        return await sessions.transition(db, hubs, session_id, S.declined)
    await _decrement_stock(db, session_id)
    return await sessions.transition(db, hubs, session_id, S.accepted)


async def _decrement_stock(db: AsyncSession, session_id: uuid.UUID) -> None:
    live = await views.live_lines(db, session_id)
    for line, product in live:
        if line.qty > product.available_stock:
            raise AppError(
                "INSUFFICIENT_STOCK", f"Only {product.available_stock} of {product.product_name} left", 409
            )
    for line, product in live:
        product.available_stock -= line.qty
    await db.commit()


async def edit_in_person(
    db: AsyncSession, hubs: Hubs, session_id: uuid.UUID, edits: list[BasketEditLine]
) -> MerchantBasket:
    """Merchant rewrites the basket while the shopkeeper is with the customer. Below minimum is
    allowed and flagged."""
    session = await sessions.get_session(db, session_id)
    sessions.require_state(session, S.in_person)
    ids = [e.product_id for e in edits]
    if len(set(ids)) != len(ids):
        raise AppError("VALIDATION_ERROR", "One line per product", 422, "lines")
    products = {p.product_id: p for p in await db.scalars(select(Product).where(Product.product_id.in_(ids)))}
    for e in edits:
        product = products.get(e.product_id)
        if product is None:
            raise AppError("PRODUCT_NOT_FOUND", f"Unknown product {e.product_id}", 404)
        if e.qty < 1 or e.line_total <= 0:
            raise AppError("VALIDATION_ERROR", "Quantity and amount must be above 0", 422, "lines")
        if e.qty > product.available_stock:
            raise AppError(
                "INSUFFICIENT_STOCK", f"Only {product.available_stock} of {product.product_name} left", 409
            )
    now = datetime.now(UTC)
    for line in (await _live_by_product(db, session_id)).values():
        line.removed_at = now
    for e in edits:
        db.add(
            BasketLine(
                session_id=session_id,
                product_id=e.product_id,
                qty=e.qty,
                line_total=e.line_total,
                below_minimum=e.line_total < products[e.product_id].minimum_price * e.qty,
                edited_by_merchant=True,
            )
        )
    await db.commit()
    await _push(db, hubs, session_id, "edit")
    return await views.merchant_basket(db, session_id)
