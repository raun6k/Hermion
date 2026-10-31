"""Hermion asks the shopkeeper about an offer below the floor. Spec: docs/engine.md#escalation.

The engine flags an evaluation `escalation_eligible` (merchant's `escalation` setting, cap unused); the
tool `ask_shopkeeper` opens the check; the shopkeeper accepts, counters or declines from the dashboard. A
merchant-set price becomes a normal accepted evaluation (never below the product minimum) and goes through
the usual basket consent.
"""

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Offer, Session
from app.engine.basket import split_basket_amount
from app.engine.escalation import CAP_PER_SESSION
from app.engine.types import OfferItem
from app.schemas.common import AppError
from app.schemas.events import DealRequestEvent, PriceCheck
from app.services import catalog, consent, sessions, trace, views
from app.services.hub import Hubs


async def ask(
    db: AsyncSession, hubs: Hubs, session_id: uuid.UUID, evaluation_id: uuid.UUID
) -> dict[str, Any]:
    session = await sessions.get_session(db, session_id)
    sessions.require_state(session, sessions.S.negotiating)
    offer = await db.get(Offer, evaluation_id)
    if offer is None or offer.session_id != session_id:
        raise AppError("EVALUATION_NOT_FOUND", "Unknown evaluation for this session", 404)
    merchant = await catalog.get_merchant(db, session.merchant_id)
    if (
        merchant.escalation == "never"
        or not offer.signals.get("escalation_eligible")
        or session.escalations >= CAP_PER_SESSION
        or session.pending_check is not None
    ):
        raise AppError("ESCALATION_NOT_ALLOWED", "Hermion cannot ask the shopkeeper about this offer", 409)
    check = PriceCheck(evaluation_id=offer.id, items=offer.items, offered_amount=offer.offered_amount)
    session.pending_check = check.model_dump(mode="json")
    session.escalations += 1
    await db.commit()
    await hubs.merchant.broadcast(
        DealRequestEvent(
            session_id=session_id, basket=await views.merchant_basket(db, session_id), price_check=check
        )
    )
    return {"asked": True, "note": "Tell the customer you are checking with the shopkeeper. Quote no price."}


async def answer(
    db: AsyncSession,
    hubs: Hubs,
    session_id: uuid.UUID,
    action: str,
    price: Decimal | None,
) -> tuple[str, Offer | None]:
    """Shopkeeper's reply. Returns (action, the accepted evaluation or None for a decline)."""
    session: Session = await sessions.get_session(db, session_id)
    check = session.pending_check
    if check is None:
        raise AppError("NO_PRICE_CHECK", "There is no open price check for this customer", 409)
    asked = await db.get(Offer, uuid.UUID(check["evaluation_id"]))
    items = [OfferItem(i["product_id"], i["qty"]) for i in check["items"]]
    session.pending_check = None
    if action == "decline":
        await db.commit()
        return action, None

    offered = Decimal(check["offered_amount"])
    if asked is not None and asked.offer_scope == "per_unit":
        offered *= items[0].qty
    amount = offered if action == "accept" else price
    if amount is None or amount != amount.to_integral_value():
        session.pending_check = check
        raise AppError("VALIDATION_ERROR", "Give a whole-rupee price", 422, "price")
    products = await catalog.product_terms(db, [i.product_id for i in items])
    minimum = {i.product_id: products[i.product_id].minimum_price * i.qty for i in items}
    if amount < sum(minimum.values(), Decimal(0)):
        session.pending_check = check
        await db.commit()
        raise AppError(
            "BELOW_MINIMUM",
            "That is below a product's minimum price; change the minimum in Products first",
            422,
            "price",
        )
    listed = sum((products[i.product_id].listed_price * i.qty for i in items), Decimal(0))
    amount = min(amount, listed)
    lines = split_basket_amount(amount, minimum, items)
    offer = Offer(
        session_id=session_id,
        items=[{"product_id": i.product_id, "qty": i.qty} for i in items],
        offered_amount=Decimal(check["offered_amount"]),
        offer_scope="basket" if len(items) > 1 else "line",
        signals={"active": [], "buy_now": False, "bundle": False, "merchant": True},
        decision="accept",
        price=amount,
        line_prices=[
            {"product_id": ln.product_id, "qty": ln.qty, "line_total": str(ln.line_total)} for ln in lines
        ],
        reason_code="MERCHANT_PRICE",
        round=0,
        final=True,
    )
    db.add(offer)
    await db.commit()
    await db.refresh(offer)
    await trace.push_offer(hubs.merchant, session_id, offer)
    await consent.open_consent(db, session, offer.id)
    return action, offer
