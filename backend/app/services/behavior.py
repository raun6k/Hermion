"""Customer behaviour features from the session's offers and messages. Spec: docs/engine.md#customer-read."""

import re
import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Message, Offer, Product
from app.engine.behavior import BehaviorFeatures, Profile, classify
from app.engine.types import OfferItem

_WALK_AWAY = re.compile(
    r"check (it )?elsewhere|other (shop|store)|leave it|forget it|not interested|nahi chahiye|"
    r"chhod ?o|rehne do|somewhere else|will go|i'?ll go",
    re.IGNORECASE,
)
_HESITATION = re.compile(
    r"\b(think|compare|cheaper|later|sochta|sochti|dekhta|dekhti|not sure|hmm)\b|baad mein", re.IGNORECASE
)


def _ratio(offer: Offer, listed: dict[str, Decimal]) -> Decimal | None:
    total = sum((listed.get(i["product_id"], Decimal(0)) * i["qty"] for i in offer.items), Decimal(0))
    if total <= 0:
        return None
    amount = offer.offered_amount
    if offer.offer_scope == "per_unit":
        amount *= offer.items[0]["qty"]
    return amount / total


async def read_customer(
    db: AsyncSession,
    session_id: uuid.UUID,
    items: list[OfferItem],
    offered_total: Decimal,
    buy_now: bool,
) -> Profile:
    products = {p.product_id: p.listed_price for p in await db.scalars(select(Product))}
    prior = [
        o
        for o in await db.scalars(
            select(Offer).where(Offer.session_id == session_id).order_by(Offer.created_at, Offer.id)
        )
        if not o.signals.get("bundle")
    ]
    ratios = [r for o in prior if (r := _ratio(o, products)) is not None]
    listed_now = sum((products.get(i.product_id, Decimal(0)) * i.qty for i in items), Decimal(0))
    if listed_now > 0:
        ratios.append(offered_total / listed_now)
    amounts = [o.offered_amount for o in prior] + [offered_total]
    repeats = sum(1 for a, b in zip(amounts, amounts[1:], strict=False) if a == b)
    texts = [
        m.text
        for m in await db.scalars(
            select(Message).where(
                Message.session_id == session_id, Message.channel == "customer", Message.speaker == "customer"
            )
        )
    ]
    walk = any(_WALK_AWAY.search(t) for t in texts[-2:])
    return classify(
        BehaviorFeatures(
            offers=len(ratios),
            opening_ratio=ratios[0] if ratios else None,
            last_step_ratio=(ratios[-1] - ratios[-2]) if len(ratios) >= 2 else None,
            repeats=repeats,
            hesitation=sum(1 for t in texts if _HESITATION.search(t)),
            qty_or_bundle=len(items) > 1 or any(i.qty >= 2 for i in items),
            buy_now=buy_now,
            walk_away=walk,
        )
    )
