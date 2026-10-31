"""Read models: baskets, summaries, mandates and the full session trace. No writes, no pushes."""

import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    TERMINAL_STATES,
    BasketLine,
    Mandate,
    Message,
    Offer,
    Product,
    Session,
    StateChange,
    ToolCallTrace,
    TurnTiming,
)
from app.schemas.common import AppError
from app.schemas.merchant import (
    MandateProposal,
    MandateRule,
    MerchantBasket,
    MerchantBasketLine,
    SessionSummary,
    SessionTrace,
    TraceMessage,
    TraceOffer,
    TraceStateChange,
    TraceTiming,
    TraceToolCall,
)
from app.schemas.public import BasketLinePublic, BasketPublic

ZERO = Decimal(0)


async def live_lines(db: AsyncSession, session_id: uuid.UUID) -> list[tuple[BasketLine, Product]]:
    rows = await db.execute(
        select(BasketLine, Product)
        .join(Product, Product.product_id == BasketLine.product_id)
        .where(BasketLine.session_id == session_id, BasketLine.removed_at.is_(None))
        .order_by(Product.product_id)
    )
    return [(line, product) for line, product in rows.all()]


async def public_basket(db: AsyncSession, session_id: uuid.UUID) -> BasketPublic:
    rows = await live_lines(db, session_id)
    lines = [
        BasketLinePublic(
            product_id=p.product_id,
            product_name=p.product_name,
            qty=line.qty,
            line_total=line.line_total,
            listed_total=p.listed_price * line.qty,
        )
        for line, p in rows
    ]
    return BasketPublic(lines=lines, total=sum((ln.line_total for ln in lines), ZERO))


async def merchant_basket(db: AsyncSession, session_id: uuid.UUID) -> MerchantBasket:
    rows = await live_lines(db, session_id)
    lines = [
        MerchantBasketLine(
            product_id=p.product_id,
            product_name=p.product_name,
            qty=line.qty,
            listed_price=p.listed_price,
            line_total=line.line_total,
            contribution=line.line_total - p.unit_cost * line.qty,
            below_minimum=line.below_minimum,
        )
        for line, p in rows
    ]
    return MerchantBasket(
        lines=lines,
        total=sum((ln.line_total for ln in lines), ZERO),
        contribution=sum((ln.contribution for ln in lines), ZERO),
    )


def _summary(session: Session, line_count: int, total: Decimal | None, guest: int = 0) -> SessionSummary:
    return SessionSummary(
        customer_name=session.customer_name,
        price_check=session.pending_check,
        display_name=session.customer_name or f"Guest {guest}",
        session_id=session.session_id,
        state=session.state,
        language=session.language,
        started_at=session.started_at,
        ended_at=session.ended_at,
        line_count=line_count,
        basket_total=total if line_count else None,
    )


async def session_summary(db: AsyncSession, session: Session) -> SessionSummary:
    count, total = (
        await db.execute(
            select(func.count(BasketLine.id), func.coalesce(func.sum(BasketLine.line_total), ZERO)).where(
                BasketLine.session_id == session.session_id, BasketLine.removed_at.is_(None)
            )
        )
    ).one()
    guest = await db.scalar(
        select(func.count(Session.session_id)).where(
            Session.merchant_id == session.merchant_id,
            Session.customer_name.is_(None),
            Session.started_at <= session.started_at,
        )
    )
    return _summary(session, count, total, guest or 0)


async def list_summaries(db: AsyncSession, scope: str, merchant_id: str = "M001") -> list[SessionSummary]:
    terminal = Session.state.in_(TERMINAL_STATES)
    sessions = await db.scalars(
        select(Session)
        .where(terminal if scope == "past" else ~terminal, Session.merchant_id == merchant_id)
        .order_by(Session.started_at.desc())
    )
    return [await session_summary(db, s) for s in sessions]


def mandate_proposal(mandate: Mandate) -> MandateProposal:
    raw = mandate.rules.get("rules", [])
    return MandateProposal(
        mandate_id=mandate.id,
        readable=mandate.readable,
        rules=[
            MandateRule(
                product_id=r["product_id"],
                settle_at=Decimal(r["settle_at"]),
                when={k: r[k] for k in ("min_qty", "with_product_id") if r.get(k) is not None},
            )
            for r in raw
        ],
        limited_product_ids=[r["product_id"] for r in raw if r.get("limited")],
        confirmed=mandate.confirmed_at is not None,
    )


async def latest_mandate(db: AsyncSession, session_id: uuid.UUID) -> Mandate | None:
    """The newest mandate of the session that has not been replaced (proposed or confirmed)."""
    return await db.scalar(
        select(Mandate)
        .where(Mandate.session_id == session_id, Mandate.replaced_at.is_(None))
        .order_by(Mandate.confirmed_at.desc().nulls_last(), Mandate.id)
        .limit(1)
    )


async def active_mandate(db: AsyncSession, session_id: uuid.UUID) -> Mandate | None:
    return await db.scalar(
        select(Mandate)
        .where(
            Mandate.session_id == session_id,
            Mandate.confirmed_at.is_not(None),
            Mandate.replaced_at.is_(None),
        )
        .order_by(Mandate.confirmed_at.desc())
        .limit(1)
    )


async def session_trace(db: AsyncSession, session_id: uuid.UUID) -> SessionTrace:
    session = await db.get(Session, session_id)
    if session is None:
        raise AppError("SESSION_NOT_FOUND", "Unknown session", 404)
    messages = await db.scalars(
        select(Message).where(Message.session_id == session_id).order_by(Message.created_at, Message.id)
    )
    offers = await db.scalars(
        select(Offer).where(Offer.session_id == session_id).order_by(Offer.created_at, Offer.id)
    )
    tool_calls = await db.scalars(
        select(ToolCallTrace)
        .where(ToolCallTrace.session_id == session_id)
        .order_by(ToolCallTrace.created_at, ToolCallTrace.id)
    )
    changes = await db.scalars(
        select(StateChange)
        .where(StateChange.session_id == session_id)
        .order_by(StateChange.created_at, StateChange.id)
    )
    timings = await db.scalars(
        select(TurnTiming)
        .where(TurnTiming.session_id == session_id)
        .order_by(TurnTiming.created_at, TurnTiming.id)
    )
    mandate = await latest_mandate(db, session_id)
    basket = await merchant_basket(db, session_id)
    return SessionTrace(
        session=await session_summary(db, session),
        messages=[TraceMessage.model_validate(m) for m in messages],
        offers=[TraceOffer.model_validate(o) for o in offers],
        tool_calls=[TraceToolCall.model_validate(t) for t in tool_calls],
        state_changes=[TraceStateChange.model_validate(c) for c in changes],
        turn_timings=[TraceTiming.model_validate(t) for t in timings],
        basket=basket if basket.lines else None,
        mandate=mandate_proposal(mandate) if mandate else None,
    )


async def recent_transcripts(db: AsyncSession, session_id: uuid.UUID, limit: int = 20) -> list[Message]:
    rows = await db.scalars(
        select(Message)
        .where(Message.session_id == session_id, Message.channel == "customer")
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(limit)
    )
    return list(reversed(list(rows)))
