"""Merchant-scoped statistics, all computed from real rows (sessions, offers, baskets, tool calls)."""

from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    TERMINAL_STATES,
    BasketLine,
    Message,
    Offer,
    Product,
    Session,
    SessionState,
    StateChange,
    ToolCallTrace,
    TurnTiming,
)
from app.languages import LANGUAGES
from app.schemas.merchant import DayPoint, Funnel, NamedCount, Stats, TopProduct


def _share(part: int, whole: int) -> Decimal:
    return (Decimal(part) / Decimal(whole)).quantize(Decimal("0.01")) if whole else Decimal(0)


async def merchant_stats(db: AsyncSession, merchant_id: str, days: int | None = None) -> Stats:
    since = datetime.now(UTC) - timedelta(days=days) if days else None
    in_window = [Session.merchant_id == merchant_id] + ([Session.started_at >= since] if since else [])
    rows = list(await db.scalars(select(Session).where(*in_window)))
    ids = [s.session_id for s in rows]
    accepted = [s for s in rows if s.state is SessionState.accepted]
    accepted_ids = [s.session_id for s in accepted]

    offers = await db.scalar(select(func.count(Offer.id)).where(Offer.session_id.in_(ids))) if ids else 0

    lines = []
    if accepted_ids:
        lines = list(
            (
                await db.execute(
                    select(BasketLine, Product, Session)
                    .join(Product, Product.product_id == BasketLine.product_id)
                    .join(Session, Session.session_id == BasketLine.session_id)
                    .where(BasketLine.session_id.in_(accepted_ids), BasketLine.removed_at.is_(None))
                )
            ).all()
        )
    listed = sum((p.listed_price * ln.qty for ln, p, _ in lines), Decimal(0))
    agreed = sum((ln.line_total for ln, _, _ in lines), Decimal(0))
    cost = sum((p.unit_cost * ln.qty for ln, p, _ in lines), Decimal(0))
    discount = (Decimal(100) * (listed - agreed) / listed) if listed else Decimal(0)

    per_day: dict[str, list] = defaultdict(lambda: [0, Decimal(0)])
    for s in accepted:
        per_day[(s.ended_at or s.started_at).date().isoformat()][0] += 1
    for ln, _, s in lines:
        per_day[(s.ended_at or s.started_at).date().isoformat()][1] += ln.line_total
    top: dict[str, list] = {}
    for ln, p, _ in lines:
        entry = top.setdefault(p.product_id, [p.product_name, 0, Decimal(0)])
        entry[1] += ln.qty
        entry[2] += ln.line_total

    funnel = await _funnel(db, rows)
    languages = Counter(s.language for s in rows if s.language)

    suggested: dict = defaultdict(set)
    for call in (
        await db.scalars(
            select(ToolCallTrace).where(
                ToolCallTrace.session_id.in_(accepted_ids), ToolCallTrace.name == "suggest_addons"
            )
        )
        if accepted_ids
        else []
    ):
        suggested[call.session_id] |= {a["product_id"] for a in call.result.get("addons", [])}
    attached = sum(
        1
        for s in accepted
        if suggested[s.session_id]
        & {ln.product_id for ln, _, sess in lines if sess.session_id == s.session_id}
    )

    finished = [s for s in rows if s.state in TERMINAL_STATES and s.ended_at]
    seconds = (
        sum(int((s.ended_at - s.started_at).total_seconds()) for s in finished) // len(finished)
        if finished
        else 0
    )
    agent_ms = [
        int(t.measurements["agent_ms"])
        for t in (await db.scalars(select(TurnTiming).where(TurnTiming.session_id.in_(ids))) if ids else [])
        if t.measurements.get("agent_ms") is not None
    ]
    abandoned = 0
    if ids:
        with_lines = set(
            await db.scalars(select(BasketLine.session_id).where(BasketLine.session_id.in_(ids)).distinct())
        )
        abandoned = sum(
            1
            for s in rows
            if s.state in (SessionState.exited, SessionState.declined) and s.session_id in with_lines
        )

    return Stats(
        sessions=len(rows),
        offers=offers or 0,
        deals=len(accepted),
        avg_discount_pct=discount.quantize(Decimal("0.01")),
        total_contribution=agreed - cost,
        days=days,
        revenue_won=agreed,
        discount_given=listed - agreed,
        funnel=funnel,
        per_day=[DayPoint(day=d, deals=v[0], revenue=v[1]) for d, v in sorted(per_day.items())],
        top_products=[
            TopProduct(product_id=pid, product_name=n, units=u, revenue=r)
            for pid, (n, u, r) in sorted(top.items(), key=lambda kv: -kv[1][2])[:5]
        ],
        language_mix=[
            NamedCount(name=LANGUAGES[c].name if c in LANGUAGES else c, value=n)
            for c, n in languages.most_common()
        ],
        upsell_attach_rate=_share(attached, len(accepted)),
        abandoned_baskets=abandoned,
        escalation_rate=_share(sum(1 for s in rows if s.escalations > 0), len(rows)),
        total_negotiation_seconds=seconds,
        avg_response_ms=sum(agent_ms) // len(agent_ms) if agent_ms else None,
        outcomes=[
            NamedCount(name=name, value=n)
            for name, n in (
                ("accepted", len(accepted)),
                ("declined", sum(1 for s in rows if s.state is SessionState.declined)),
                ("exited", sum(1 for s in rows if s.state is SessionState.exited)),
                ("open", sum(1 for s in rows if s.state not in TERMINAL_STATES)),
            )
        ],
        per_hour_utc=[
            NamedCount(name=str(h), value=n)
            for h, n in sorted(Counter(s.started_at.astimezone(UTC).hour for s in rows).items())
        ],
    )


async def _funnel(db: AsyncSession, rows: list[Session]) -> Funnel:
    ids = [s.session_id for s in rows]
    if not ids:
        return Funnel(scanned=0, started=0, offered=0, in_basket=0, confirmed=0, accepted=0)
    started = set(
        await db.scalars(
            select(Message.session_id)
            .where(Message.session_id.in_(ids), Message.channel == "customer", Message.speaker == "customer")
            .distinct()
        )
    )
    offered = set(
        await db.scalars(
            select(Offer.session_id).where(Offer.session_id.in_(ids), Offer.round > 0).distinct()
        )
    )
    in_basket = set(
        await db.scalars(select(BasketLine.session_id).where(BasketLine.session_id.in_(ids)).distinct())
    )
    confirmed = set(
        await db.scalars(
            select(StateChange.session_id)
            .where(StateChange.session_id.in_(ids), StateChange.to_state == "pending_merchant")
            .distinct()
        )
    )
    return Funnel(
        scanned=len(ids),
        started=len(started),
        offered=len(offered),
        in_basket=len(in_basket),
        confirmed=len(confirmed),
        accepted=sum(1 for s in rows if s.state is SessionState.accepted),
    )
