"""Trace store: every message / offer / basket / mandate change, pushed silently to merchants."""

import asyncio
import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import Merchant, Message, Offer, Session, ToolCallTrace, TurnTiming
from app.db.session import sessionmaker
from app.schemas.events import TraceEvent
from app.schemas.merchant import (
    MandateProposal,
    MerchantBasket,
    TraceMessage,
    TraceOffer,
    TraceTiming,
    TraceToolCall,
)
from app.services.hub import MerchantHub
from app.speech.translate import preserves_critical_tokens

log = logging.getLogger(__name__)


async def _translate_message(hub: MerchantHub, message_id: uuid.UUID) -> None:
    try:
        async with sessionmaker()() as db:
            msg = await db.get(Message, message_id)
            if msg is None:
                return
            session = await db.get(Session, msg.session_id)
            merchant = await db.get(Merchant, session.merchant_id) if session else None
            if merchant is None:
                return
            translated = await hub.translator.translate(
                msg.text, msg.language, get_settings().merchant_language
            )
            if not preserves_critical_tokens(msg.text, translated):
                log.warning("Translation changed a protected size or number for message %s", message_id)
                return
            msg.text_translated = translated
            await db.commit()
            data = TraceMessage.model_validate(msg).model_dump(mode="json")
            await hub.broadcast(TraceEvent(session_id=msg.session_id, kind="message", data=data))
    except asyncio.CancelledError:
        raise
    except Exception:
        log.exception("Trace translation failed for message %s", message_id)


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
    if channel == "customer" and hub.translator is not None:
        task = asyncio.create_task(_translate_message(hub, msg.id))
        hub.translation_tasks.add(task)
        task.add_done_callback(hub.translation_tasks.discard)
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


async def record_timing(
    db: AsyncSession,
    hub: MerchantHub,
    session_id: uuid.UUID,
    message_id: uuid.UUID,
    measurements: dict[str, Any],
) -> uuid.UUID:
    row = TurnTiming(session_id=session_id, message_id=message_id, measurements=measurements)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    await hub.broadcast(
        TraceEvent(
            session_id=session_id, kind="timing", data=TraceTiming.model_validate(row).model_dump(mode="json")
        )
    )
    return row.id


async def record_first_audio(hub: MerchantHub, timing_id: uuid.UUID, elapsed_ms: int) -> None:
    try:
        async with sessionmaker()() as db:
            row = await db.get(TurnTiming, timing_id)
            if row is None:
                return
            row.measurements = {**row.measurements, "speech_end_to_first_audio_ms": elapsed_ms}
            await db.commit()
            await hub.broadcast(
                TraceEvent(
                    session_id=row.session_id,
                    kind="timing",
                    data=TraceTiming.model_validate(row).model_dump(mode="json"),
                )
            )
    except Exception:
        log.exception("Failed to record first-audio timing %s", timing_id)
