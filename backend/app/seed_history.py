"""Synthetic merchant history replayed through the real services and deterministic engine.

Run: `uv run python -m app.seed_history` (add `--clear` to purge synthetic rows). The generator
maintains at most 10 active and 30 past sessions per merchant, preserving non-synthetic sessions.
"""

import argparse
import asyncio
import logging
import random
import uuid
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import DatabaseSettings
from app.db.models import (
    TERMINAL_STATES,
    BasketLine,
    Mandate,
    Merchant,
    Message,
    Offer,
    Product,
    Session,
    SessionState,
    StateChange,
    ToolCallTrace,
    TurnTiming,
)
from app.engine.types import OfferItem, OfferScope
from app.languages import LANGUAGES
from app.schemas.merchant import ReviewAction
from app.services import basket, consent, offers, sessions
from app.services.hub import CustomerHub, Hubs, MerchantHub

log = logging.getLogger("seed_history")
DAYS = 30
ACTIVE_LIMIT = 10
PAST_LIMIT = 30
TIMED = (Message, Offer, StateChange, ToolCallTrace, TurnTiming)
NAMES = [
    "Asha",
    "Ravi",
    "Meera",
    "Kiran",
    "Sana",
    "Vikram",
    "Lakshmi",
    "Imran",
    "Priya",
    "Arjun",
    "Ananya",
    "Dev",
    "Ishita",
    "Kabir",
    "Nisha",
    "Rahul",
    "Tara",
    "Zoya",
    "Neel",
    "Farah",
]


def _hubs() -> Hubs:
    return Hubs(MerchantHub(), CustomerHub())


def _language(merchant: Merchant) -> str:
    """Use English for the scripted English transcript, chosen from the shop's enabled languages."""
    enabled = [code for code in (merchant.languages or []) if code in LANGUAGES]
    if not enabled:
        return next(iter(LANGUAGES))
    return next((code for code in enabled if LANGUAGES[code].name == "English"), enabled[0])


async def _shift(db: AsyncSession, session_id: uuid.UUID, delta: timedelta) -> None:
    """Move every row of a replayed session back in time (NULL timestamps stay NULL)."""
    for model in TIMED:
        await db.execute(
            update(model).where(model.session_id == session_id).values(created_at=model.created_at - delta)
        )
    await db.execute(
        update(BasketLine)
        .where(BasketLine.session_id == session_id, BasketLine.removed_at.is_not(None))
        .values(removed_at=BasketLine.removed_at - delta)
    )
    await db.execute(
        update(Session)
        .where(Session.session_id == session_id)
        .values(started_at=Session.started_at - delta, ended_at=Session.ended_at - delta)
    )


async def _say(db: AsyncSession, sid: uuid.UUID, speaker: str, text: str, language: str) -> Message:
    message = Message(
        session_id=sid,
        channel="customer",
        speaker=speaker,
        text=text,
        language=language,
    )
    db.add(message)
    await db.flush()
    return message


async def _negotiate(
    db: AsyncSession,
    hubs: Hubs,
    rng: random.Random,
    sid: uuid.UUID,
    language: str,
    items: list[OfferItem],
    products: list[Product],
    *,
    aim_for_acceptance: bool,
) -> uuid.UUID | None:
    """Record a short, coherent exchange; any Hermion amount comes from the engine result."""
    by_id = {p.product_id: p for p in products}
    names = [by_id[item.product_id].product_name for item in items]
    label = " and ".join(names)
    listed = sum((by_id[item.product_id].listed_price * item.qty for item in items), Decimal(0))
    opening_factor = rng.choice((Decimal("0.68"), Decimal("0.74"), Decimal("0.80"), Decimal("0.86")))
    amount = (listed * opening_factor).to_integral_value()
    if not aim_for_acceptance:
        floor = sum((by_id[item.product_id].minimum_price * item.qty for item in items), Decimal(0))
        amount = max(Decimal(1), min(amount, floor - Decimal(1)))
    scope = OfferScope.line if len(items) == 1 else OfferScope.basket

    for _turn in range(3):
        await _say(
            db,
            sid,
            "customer",
            f"I like the {label}. Could you do ₹{int(amount)} for this?",
            language,
        )
        result = await offers.evaluate(
            db,
            hubs,
            sid,
            items,
            amount,
            scope,
            buy_now=False,
        )
        price = Decimal(result["price"]) if result.get("price") is not None else None
        if result["decision"] == "accept" and price is not None:
            reply = f"That works. I can do ₹{int(price)} for the {label}. Shall I add it to your basket?"
        elif price is not None and result["reason_code"] == "FIXED_PRICE":
            reply = f"The {label} is fixed at ₹{int(price)}. Would you like to continue?"
        elif price is not None:
            reply = f"I can offer ₹{int(price)} for the {label}. Would that work for you?"
        else:
            reply = f"I can't accept that amount for the {label}. Would you like to try another price?"
        await _say(db, sid, "hermion", reply, language)
        await db.commit()

        if result["decision"] == "accept":
            return uuid.UUID(result["evaluation_id"])
        if price is None or not aim_for_acceptance:
            return None
        # Taking Hermion's logged counter closes on the next engine evaluation.
        amount = price

    return None


async def _add_basket(
    db: AsyncSession,
    hubs: Hubs,
    sid: uuid.UUID,
    evaluation_id: uuid.UUID,
    language: str,
    item_label: str,
    amount: Decimal,
) -> None:
    await basket.add_from_evaluation(db, hubs, sid, evaluation_id)
    session = await sessions.get_session(db, sid)
    await consent.clear(db, session)
    await _say(
        db,
        sid,
        "hermion",
        f"I've added the {item_label} to your basket at ₹{int(amount)}.",
        language,
    )
    await db.commit()


async def _one_session(
    db: AsyncSession,
    rng: random.Random,
    merchant: Merchant,
    products: list[Product],
    outcome: str,
) -> uuid.UUID:
    """Build one named customer journey. Outcome controls only the final session state."""
    hubs = _hubs()
    session = await sessions.create_session(db, merchant.qr_token, f"seed-{uuid.uuid4()}")
    sid = session.session_id
    language = _language(merchant)
    session.source = "seed"
    session.customer_name = rng.choice(NAMES)
    session.language = language
    await db.commit()
    await sessions.transition(db, hubs, sid, SessionState.discovery)

    available = [p for p in products if p.available_stock > 0]
    if not available:
        await _say(db, sid, "customer", "I'm looking for something for everyday use.", language)
        await _say(db, sid, "hermion", "I can help you browse the shop. What are you looking for?", language)
        await db.commit()
        if outcome != "active_browse":
            await sessions.exit_session(db, hubs, sid)
        return sid

    product = rng.choice(available)
    qty = 2 if product.available_stock > 2 and rng.random() < 0.22 else 1
    items = [OfferItem(product.product_id, qty)]
    label = product.product_name
    session.intent = {"looking_for": label, "quantity": qty}
    await _say(db, sid, "customer", f"Hi, I'm looking for a {label}.", language)
    await _say(
        db,
        sid,
        "hermion",
        f"I can help with the {label}. What price did you have in mind?",
        language,
    )
    await db.commit()

    if outcome == "active_browse":
        return sid

    want_basket = outcome in {"active_basket", "active_approval", "accepted", "declined", "exit_basket"}
    evaluation_id = await _negotiate(
        db,
        hubs,
        rng,
        sid,
        language,
        items,
        products,
        aim_for_acceptance=want_basket,
    )
    if evaluation_id is None:
        await _say(db, sid, "customer", "I'll have a look around and come back later.", language)
        await db.commit()
        if outcome not in {"active_negotiate", "active_basket"}:
            await sessions.exit_session(db, hubs, sid)
        return sid

    accepted_offer = await db.get(Offer, evaluation_id)
    amount = accepted_offer.price or accepted_offer.offered_amount
    if outcome in {"active_basket", "active_approval", "accepted", "declined", "exit_basket"}:
        await _add_basket(db, hubs, sid, evaluation_id, language, label, amount)

    if outcome == "active_approval":
        await _say(db, sid, "customer", "Please send my basket to the shop for review.", language)
        await db.commit()
        await basket.confirm(db, hubs, sid)
    elif outcome in {"accepted", "declined"}:
        await _say(db, sid, "customer", "Please send my basket to the shop for review.", language)
        await db.commit()
        await basket.confirm(db, hubs, sid)
        action = ReviewAction.accept if outcome == "accepted" else ReviewAction.decline
        await basket.review(db, hubs, sid, action)
    elif outcome in {"exit_no_basket", "exit_basket"}:
        await _say(db, sid, "customer", "Thanks, I'll come back to the shop later.", language)
        await db.commit()
        await sessions.exit_session(db, hubs, sid)

    return sid


async def _restore_stock(db: AsyncSession, products: list[Product], stock: dict[str, int]) -> None:
    """Each synthetic customer sees the original demo inventory; replays don't consume real stock."""
    for product in products:
        product.available_stock = stock[product.product_id]
    await db.commit()


async def generate(db: AsyncSession, seed: int = 7, days: int = DAYS) -> int:
    """Fill each merchant to the session caps, counting pre-existing non-synthetic sessions."""
    rng = random.Random(seed)
    all_products = list(await db.scalars(select(Product)))
    stock = {p.product_id: p.available_stock for p in all_products}
    made = 0

    for merchant in await db.scalars(select(Merchant).order_by(Merchant.merchant_id)):
        products = [p for p in all_products if p.merchant_id == merchant.merchant_id]
        if not products:
            log.warning("%s has no products; no synthetic sessions generated", merchant.merchant_id)
            continue

        existing_active = await db.scalar(
            select(func.count())
            .select_from(Session)
            .where(
                Session.merchant_id == merchant.merchant_id,
                Session.source != "seed",
                Session.state.not_in(TERMINAL_STATES),
            )
        )
        existing_past = await db.scalar(
            select(func.count())
            .select_from(Session)
            .where(
                Session.merchant_id == merchant.merchant_id,
                Session.source != "seed",
                Session.state.in_(TERMINAL_STATES),
            )
        )
        active_count = max(0, ACTIVE_LIMIT - (existing_active or 0))
        past_count = max(0, PAST_LIMIT - (existing_past or 0))

        past_outcomes = [
            "accepted" if i < 14 else "declined" if i < 21 else "exit_basket" if i < 26 else "exit_no_basket"
            for i in range(past_count)
        ]
        rng.shuffle(past_outcomes)
        for index, outcome in enumerate(past_outcomes):
            await _restore_stock(db, all_products, stock)
            sid = await _one_session(db, rng, merchant, products, outcome)
            age_days = (index % max(days, 1)) + 1
            delta = timedelta(days=age_days, hours=rng.randint(0, 9), minutes=rng.randint(0, 59))
            await _shift(db, sid, delta)
            await db.commit()
            made += 1

        # Keep a few customers browsing, submit two baskets for merchant review, and leave the rest
        # negotiating with an engine-backed offer or a populated but unsubmitted basket.
        active_outcomes = ["active_browse"] * min(2, active_count)
        approval_count = min(2, max(0, active_count - len(active_outcomes)))
        active_outcomes.extend(["active_approval"] * approval_count)
        remaining = active_count - len(active_outcomes)
        active_outcomes.extend(
            "active_basket" if i % 3 != 0 else "active_negotiate" for i in range(remaining)
        )
        rng.shuffle(active_outcomes)
        for outcome in active_outcomes:
            await _restore_stock(db, all_products, stock)
            await _one_session(db, rng, merchant, products, outcome)
            await db.commit()
            made += 1

        if (existing_active or 0) > ACTIVE_LIMIT or (existing_past or 0) > PAST_LIMIT:
            log.warning(
                "%s already has %d active and %d past non-synthetic sessions; preserving them exceeds a cap",
                merchant.merchant_id,
                existing_active or 0,
                existing_past or 0,
            )

    await _restore_stock(db, all_products, stock)
    return made


async def clear(db: AsyncSession) -> None:
    ids = select(Session.session_id).where(Session.source == "seed")
    for model in (BasketLine, Offer, Mandate, TurnTiming, Message, ToolCallTrace, StateChange):
        await db.execute(delete(model).where(model.session_id.in_(ids)))
    await db.execute(delete(Session).where(Session.source == "seed"))
    await db.commit()


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    args = argparse.ArgumentParser()
    args.add_argument("--clear", action="store_true")
    flags = args.parse_args()
    engine = create_async_engine(DatabaseSettings().database_url)
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        await clear(db)
        if not flags.clear:
            log.info("generated %d synthetic sessions", await generate(db))
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
