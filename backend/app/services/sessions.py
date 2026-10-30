"""Session lifecycle. All state changes go through here (docs/architecture.md#session-state-machine)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TERMINAL_STATES, Merchant, Session, SessionState
from app.schemas.common import AppError


async def create_session(db: AsyncSession, qr_token: str, device_id: str) -> Session:
    merchant = await db.scalar(select(Merchant).where(Merchant.qr_token == qr_token))
    if merchant is None:
        raise AppError("UNKNOWN_QR", "This QR code does not belong to a Hermion shop", 404)
    active = await db.scalar(
        select(Session).where(Session.device_id == device_id, Session.state.not_in(TERMINAL_STATES))
    )
    if active is not None:
        raise AppError("SESSION_ACTIVE", "Exit your current session to scan again", 409)
    session = Session(merchant_id=merchant.merchant_id, device_id=device_id, state=SessionState.intro)
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def get_session(db: AsyncSession, session_id: uuid.UUID) -> Session:
    session = await db.get(Session, session_id)
    if session is None:
        raise AppError("SESSION_NOT_FOUND", "Unknown session", 404)
    return session


async def exit_session(db: AsyncSession, session_id: uuid.UUID) -> Session:
    """Idempotent. Skeleton keeps this so a device can start a new session; full rules come later."""
    session = await get_session(db, session_id)
    if session.state not in TERMINAL_STATES:
        session.state = SessionState.exited
        session.ended_at = datetime.now(UTC)
        await db.commit()
    return session


async def transition(db: AsyncSession, session_id: uuid.UUID, to: SessionState) -> Session:
    """Validated state change per the state machine. Built in Stage 1 (lane B)."""
    raise NotImplementedError
