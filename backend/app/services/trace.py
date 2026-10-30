"""Trace store: every message / offer / basket / mandate change, pushed silently to merchants."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Message
from app.schemas.events import TraceEvent
from app.schemas.merchant import TraceMessage
from app.services.hub import MerchantHub


async def record_message(
    db: AsyncSession,
    hub: MerchantHub,
    session_id: uuid.UUID,
    *,
    channel: str,
    speaker: str,
    text: str,
    language: str | None = None,
) -> Message:
    msg = Message(session_id=session_id, channel=channel, speaker=speaker, text=text, language=language)
    db.add(msg)
    await db.commit()
    await db.refresh(msg)
    data = TraceMessage.model_validate(msg).model_dump(mode="json")
    await hub.broadcast(TraceEvent(session_id=session_id, kind="message", data=data))
    return msg
