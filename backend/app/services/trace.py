"""Trace store: every message / offer / basket / mandate change, pushed silently to merchants."""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Message, Offer, ToolCallTrace
from app.schemas.events import TraceEvent
from app.schemas.merchant import MandateProposal, MerchantBasket, TraceMessage, TraceOffer, TraceToolCall
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


async def push_offer(hub: MerchantHub, session_id: uuid.UUID, offer: Offer) -> None:
    data = TraceOffer.model_validate(offer).model_dump(mode="json")
    await hub.broadcast(TraceEvent(session_id=session_id, kind="offer", data=data))


async def push_basket(
    hub: MerchantHub, session_id: uuid.UUID, action: str, basket: MerchantBasket, **extra: Any
) -> None:
    data = {"action": action, "basket": basket.model_dump(mode="json"), **extra}
    await hub.broadcast(TraceEvent(session_id=session_id, kind="basket", data=data))


async def push_mandate(
    hub: MerchantHub, session_id: uuid.UUID, action: str, mandate: MandateProposal
) -> None:
    data = {"action": action, "mandate": mandate.model_dump(mode="json")}
    await hub.broadcast(TraceEvent(session_id=session_id, kind="mandate", data=data))


async def record_tool_call(
    db: AsyncSession,
    hub: MerchantHub,
    session_id: uuid.UUID,
    channel: str,
    name: str,
    arguments: dict[str, Any],
    result: dict[str, Any],
) -> None:
    row = ToolCallTrace(session_id=session_id, channel=channel, name=name, arguments=arguments, result=result)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    data = TraceToolCall.model_validate(row).model_dump(mode="json")
    await hub.broadcast(TraceEvent(session_id=session_id, kind="tool_call", data=data))
