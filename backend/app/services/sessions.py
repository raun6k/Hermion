"""Session lifecycle. All state changes go through here (docs/architecture.md#session-state-machine)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TERMINAL_STATES, Merchant, Session, SessionState, StateChange
from app.schemas.common import AppError
from app.schemas.events import SessionStateEvent, StateEvent
from app.services.hub import Hubs

S = SessionState

# Every legal edge. Any non-terminal state may also go to `exited` (customer taps End call).
EDGES: dict[SessionState, frozenset[SessionState]] = {
    S.intro: frozenset({S.discovery}),
    S.discovery: frozenset({S.negotiating}),
    S.negotiating: frozenset({S.pending_merchant}),
    # pending_merchant -> negotiating: the customer rejoins Hermion to change the sent basket (withdraws it).
    S.pending_merchant: frozenset({S.accepted, S.declined, S.briefing, S.in_person, S.negotiating}),
    S.briefing: frozenset({S.negotiating}),
    S.in_person: frozenset({S.accepted, S.declined}),
}

# Shown to the customer on entering a state (English; the agent may localise it).
CUSTOMER_MESSAGES: dict[SessionState, str] = {
    S.pending_merchant: "The shop is reviewing your basket…",
    S.briefing: "The shop is reviewing your basket…",
    S.in_person: "The shopkeeper is coming to you",
    S.accepted: "Deal confirmed! The shopkeeper accepted your basket.",
    S.declined: "Sorry, the shop could not accept this basket. Thank you for visiting!",
}


def can_transition(current: SessionState, to: SessionState) -> bool:
    if current in TERMINAL_STATES:
        return False
    return to is S.exited or to in EDGES.get(current, frozenset())


async def get_or_create_session(
    db: AsyncSession, qr_token: str, device_id: str, customer_name: str | None = None
) -> tuple[Session, bool]:
    """Scanning again resumes this device's live session at this shop; returns (session, created)."""
    merchant = await db.scalar(select(Merchant).where(Merchant.qr_token == qr_token))
    if merchant is None:
        raise AppError("UNKNOWN_QR", "This QR code does not belong to a Hermion shop", 404)
    active = await db.scalar(
        select(Session)
        .where(
            Session.merchant_id == merchant.merchant_id,
            Session.device_id == device_id,
            Session.state.not_in(TERMINAL_STATES),
        )
        .order_by(Session.started_at.desc())
    )
    if active is not None:
        return active, False
    session = Session(
        merchant_id=merchant.merchant_id,
        device_id=device_id,
        state=SessionState.intro,
        customer_name=customer_name,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session, True


async def create_session(db: AsyncSession, qr_token: str, device_id: str) -> Session:
    return (await get_or_create_session(db, qr_token, device_id))[0]


async def get_session(db: AsyncSession, session_id: uuid.UUID) -> Session:
    session = await db.get(Session, session_id)
    if session is None:
        raise AppError("SESSION_NOT_FOUND", "Unknown session", 404)
    return session


def require_state(session: Session, *allowed: SessionState) -> None:
    if session.state not in allowed:
        wanted = " or ".join(s.value for s in allowed)
        raise AppError("WRONG_STATE", f"Session is {session.state.value}; this needs {wanted}", 409)


async def transition(db: AsyncSession, hubs: Hubs | None, session_id: uuid.UUID, to: SessionState) -> Session:
    """Validated state change; pushes `state` to the customer and `session_state` to merchants."""
    session = await get_session(db, session_id)
    if not can_transition(session.state, to):
        raise AppError("WRONG_STATE", f"Cannot go from {session.state.value} to {to.value}", 409)
    db.add(StateChange(session_id=session_id, from_state=session.state.value, to_state=to.value))
    session.state = to
    if to in TERMINAL_STATES:
        session.ended_at = datetime.now(UTC)
    await db.commit()
    if hubs is not None:
        await hubs.customer.send(session_id, StateEvent(state=to, message=CUSTOMER_MESSAGES.get(to)))
        await hubs.merchant.broadcast(SessionStateEvent(session_id=session_id, state=to))
    return session


async def ensure_negotiating(db: AsyncSession, hubs: Hubs | None, session: Session) -> Session:
    """First evaluate_offer / add_to_basket moves intro and discovery on to negotiating."""
    if session.state is S.intro:
        session = await transition(db, hubs, session.session_id, S.discovery)
    if session.state is S.discovery:
        session = await transition(db, hubs, session.session_id, S.negotiating)
    return session


async def rejoin(db: AsyncSession, hubs: Hubs | None, session_id: uuid.UUID) -> tuple[Session, bool]:
    """The customer taps Talk to Hermion again. A basket waiting for the shop goes back to negotiating (the
    merchant's review is withdrawn); returns (session, withdrawn). Discovery and negotiating are unchanged."""
    session = await get_session(db, session_id)
    if session.state is S.pending_merchant:
        return await transition(db, hubs, session_id, S.negotiating), True
    require_state(session, S.intro, S.discovery, S.negotiating)
    return session, False


async def exit_session(db: AsyncSession, hubs: Hubs | None, session_id: uuid.UUID) -> Session:
    """Idempotent: exiting an already-ended session returns it unchanged."""
    session = await get_session(db, session_id)
    if session.state in TERMINAL_STATES:
        return session
    return await transition(db, hubs, session_id, S.exited)
