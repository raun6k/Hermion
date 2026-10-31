"""Loads engine inputs from the DB, calls the pure engine, writes the `offers` log."""

import uuid
from dataclasses import replace
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Goal, GoalType, Merchant, Offer, Product, Session, SessionState
from app.engine.behavior import Profile, guidance
from app.engine.bundle import suggest_bundle as engine_suggest_bundle
from app.engine.concession import evaluate_offer
from app.engine.types import (
    Evaluation,
    LinePrice,
    MandateRule,
    NegotiationContext,
    OfferItem,
    OfferScope,
)
from app.schemas.events import CaptionEvent
from app.services import behavior, catalog, consent, sessions, trace, views
from app.services.hub import Hubs

# The agent only offers tools from discovery on; the service tolerates `intro` so a first offer still works.
NEGOTIATION_STATES = (SessionState.intro, SessionState.discovery, SessionState.negotiating)


def rupees(amount: Decimal) -> str:
    """Whole-rupee string for tool results and prompts ("850")."""
    return str(int(amount))


def mandate_rules(mandate_json: dict[str, Any]) -> tuple[MandateRule, ...]:
    return tuple(
        MandateRule(
            product_id=r["product_id"],
            settle_at=Decimal(r["settle_at"]),
            min_qty=r.get("min_qty"),
            with_product_id=r.get("with_product_id"),
        )
        for r in mandate_json.get("rules", [])
    )


async def build_context(
    db: AsyncSession, session: Session, items: list[OfferItem] | None = None
) -> NegotiationContext:
    """Session facts for the engine, all derived from the DB (docs/engine.md)."""
    rounds: dict[str, int] = {}
    previous: tuple[LinePrice, ...] = ()
    expected = {(i.product_id, i.qty) for i in items or []}
    for offer in await db.scalars(
        select(Offer).where(Offer.session_id == session.session_id).order_by(Offer.created_at, Offer.id)
    ):
        if offer.round > 0 and not offer.signals.get("bundle"):  # bundle quotes are not negotiation rounds
            for item in offer.items:
                rounds[item["product_id"]] = rounds.get(item["product_id"], 0) + 1
        if (
            expected
            and offer.decision == "counter"
            and {(i["product_id"], i["qty"]) for i in offer.items} == expected
        ):
            previous = tuple(
                LinePrice(p["product_id"], p["qty"], Decimal(p["line_total"])) for p in offer.line_prices
            )

    all_products = [p for p in await catalog.list_products(db, session.merchant_id)]
    clear: set[str] = set()
    preserve: set[str] = set()
    for goal in await db.scalars(select(Goal).where(Goal.merchant_id == session.merchant_id)):
        target = {p.product_id for p in all_products} if not goal.product_ids else set(goal.product_ids)
        if goal.goal_type is GoalType.clear_stock:
            clear |= target
        elif goal.goal_type is GoalType.preserve_stock:
            preserve |= target

    merchant = await db.get(Merchant, session.merchant_id)
    mandate = await views.active_mandate(db, session.session_id)
    basket = frozenset(line.product_id for line, _ in await views.live_lines(db, session.session_id))
    return NegotiationContext(
        rounds=rounds,
        basket_product_ids=basket,
        clear_stock=frozenset(clear),
        preserve_stock=frozenset(preserve),
        mandate_rules=mandate_rules(mandate.rules) if mandate else (),
        # Multi-item quotes are always available to customers; this is not a shop setting.
        bundle_allowed=True,
        last_counter=previous,
        escalation_mode=merchant.escalation if merchant else "serious",
        escalation_gap_pct=merchant.escalation_gap_pct if merchant else 5,
        escalations_used=session.escalations,
    )


def _line_prices_json(ev: Evaluation) -> list[dict[str, Any]]:
    return [
        {"product_id": lp.product_id, "qty": lp.qty, "line_total": str(lp.line_total)}
        for lp in ev.line_prices
    ]


def public_result(offer: Offer) -> dict[str, Any]:
    """What the LLM sees: the decision and price, never the threshold."""
    out: dict[str, Any] = {
        "evaluation_id": str(offer.id),
        "decision": offer.decision,
        "reason_code": offer.reason_code,
        "round": offer.round,
        "final": offer.final,
    }
    if offer.headroom:
        out["headroom"] = offer.headroom  # coarse bucket only: never the floor or target
    if offer.profile:
        out["customer_read"] = offer.profile
        out["guidance"] = guidance(Profile(offer.profile), bool(offer.signals.get("walk_away")))
    if offer.signals.get("escalation_eligible"):
        out["shopkeeper_check_possible"] = True
    if offer.signals.get("acceptable"):
        # Hermion held out for more on an offer it could have taken; it may still close at the offer.
        out["customer_offer_acceptable"] = True
    if offer.price is not None:
        out["price"] = rupees(offer.price)
        out["line_prices"] = [
            {
                "product_id": lp["product_id"],
                "qty": lp["qty"],
                "line_total": rupees(Decimal(lp["line_total"])),
            }
            for lp in offer.line_prices
        ]
    return out


async def _store(
    db: AsyncSession,
    hubs: Hubs,
    session: Session,
    items: list[OfferItem],
    offered: Decimal,
    scope: str,
    ev: Evaluation,
    *,
    buy_now: bool = False,
    bundle: bool = False,
    profile: Profile | None = None,
) -> Offer:
    mandate = await views.active_mandate(db, session.session_id) if ev.mandate_applied else None
    offer = Offer(
        session_id=session.session_id,
        items=[{"product_id": i.product_id, "qty": i.qty} for i in items],
        offered_amount=offered,
        offer_scope=scope,
        signals={
            "active": list(ev.signals),
            "buy_now": buy_now,
            "bundle": bundle,
            "escalation_eligible": ev.escalation_eligible,
            "acceptable": ev.acceptable,
            "walk_away": profile is Profile.browsing,
        },
        decision=ev.decision.value,
        price=ev.price,
        line_prices=_line_prices_json(ev),
        reason_code=ev.reason_code.value,
        round=ev.round,
        final=ev.final,
        threshold=ev.threshold,
        headroom=ev.headroom,
        profile=profile.value if profile else None,
        mandate_id=mandate.id if mandate else None,
    )
    db.add(offer)
    await db.commit()
    await db.refresh(offer)
    await trace.push_offer(hubs.merchant, session.session_id, offer)
    return offer


async def _captions(
    db: AsyncSession,
    hubs: Hubs,
    session_id: uuid.UUID,
    items: list[OfferItem],
    offer: Offer,
    offered: Decimal | None,
) -> None:
    """Price captions under the mascot: what the customer said, then what Hermion can do."""
    rows = await db.scalars(select(Product).where(Product.product_id.in_([i.product_id for i in items])))
    names = {p.product_id: p.product_name for p in rows}
    label = " + ".join(names.get(i.product_id, i.product_id) for i in items)
    if offered is not None:
        await hubs.customer.send(
            session_id, CaptionEvent(speaker="customer", product_name=label, amount=offered)
        )
    if offer.price is not None:
        await hubs.customer.send(
            session_id, CaptionEvent(speaker="hermion", product_name=label, amount=offer.price)
        )


async def _negotiable_session(db: AsyncSession, hubs: Hubs, session_id: uuid.UUID) -> Session:
    session = await sessions.get_session(db, session_id)
    sessions.require_state(session, *NEGOTIATION_STATES)
    return session


async def evaluate(
    db: AsyncSession,
    hubs: Hubs,
    session_id: uuid.UUID,
    items: list[OfferItem],
    offered_amount: Decimal,
    offer_scope: OfferScope,
    buy_now: bool,
    proposed_price: Decimal | None = None,
) -> dict[str, Any]:
    session = await _negotiable_session(db, hubs, session_id)
    products = await catalog.product_terms(db, [i.product_id for i in items])
    ctx = await build_context(db, session, items)
    total = offered_amount * items[0].qty if offer_scope is OfferScope.per_unit else offered_amount
    read = await behavior.read_customer(db, session_id, items, total, buy_now) if items else None
    ctx = replace(ctx, customer_serious=read is not Profile.lowballer)
    ev = evaluate_offer(products, items, offered_amount, offer_scope, buy_now, ctx, proposed_price)
    profile = read if ev.round > 0 else None
    offer = await _store(
        db, hubs, session, items, offered_amount, offer_scope.value, ev, buy_now=buy_now, profile=profile
    )
    stage = None
    if offer.decision == "accept":
        stage = await consent.open_consent(db, session, offer.id, buy_now)
    else:
        await consent.clear(db, session)
    if ev.round > 0:  # a real negotiation round: first one moves discovery on
        await sessions.ensure_negotiating(db, hubs, session)
        await _captions(db, hubs, session_id, items, offer, offered_amount)
    result = public_result(offer)
    if stage == "granted":
        result["add_allowed"] = True  # customer explicitly said "take it": add_to_basket may follow now
    return result


async def suggest_bundle(
    db: AsyncSession, hubs: Hubs, session_id: uuid.UUID, product_ids: list[str]
) -> dict[str, Any] | None:
    session = await _negotiable_session(db, hubs, session_id)
    items = [OfferItem(pid, 1) for pid in dict.fromkeys(product_ids)]
    products = await catalog.product_terms(db, [i.product_id for i in items])
    ctx = await build_context(db, session)
    ev = engine_suggest_bundle(products, items, ctx)
    if ev is None or ev.price is None:
        return None
    offer = await _store(db, hubs, session, items, ev.price, OfferScope.basket.value, ev, bundle=True)
    await consent.open_consent(db, session, offer.id)
    await sessions.ensure_negotiating(db, hubs, session)
    await _captions(db, hubs, session_id, items, offer, None)
    return {
        "evaluation_id": str(offer.id),
        "items": offer.items,
        "bundle_price": rupees(ev.price),
        "line_prices": public_result(offer)["line_prices"],
    }
