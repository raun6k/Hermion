"""Customer WebSocket /ws/sessions/{id} (docs/api.md#websocket-customer-wssessionsid).

Integration seam (lane B owns it). Connect replays state, basket, agent_state and the last 20 transcripts.
Turn handling is still the skeleton: keypad text -> one LLM call -> transcript back; both messages traced.
"""

import asyncio
import logging
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.agent.customer import customer_turn
from app.db.models import TERMINAL_STATES, Session
from app.db.session import sessionmaker
from app.log import session_id as session_id_ctx
from app.schemas.common import AgentState
from app.schemas.events import (
    AgentStateEvent,
    BasketEvent,
    ErrorEvent,
    LanguagePin,
    StateEvent,
    TextInput,
    TranscriptEvent,
    customer_inbound_adapter,
)
from app.services import catalog, trace, views

REPLAY_TRANSCRIPTS = 20

log = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws/sessions/{session_id}")
async def customer_ws(ws: WebSocket, session_id: UUID) -> None:
    state = ws.app.state
    session_id_ctx.set(str(session_id))
    async with sessionmaker()() as db:
        session = await db.get(Session, session_id)
        if session is None or session.state in TERMINAL_STATES:
            await ws.close(code=4404, reason="unknown or ended session")
            return
        await ws.accept()
        state.customer_hub.set(session_id, ws)

        async def send(event) -> None:
            await state.customer_hub.send(session_id, event)  # also remembers agent_state for replay

        # Reconnect replay (docs/api.md#reconnect): state, basket, last agent_state, last transcripts.
        await send(StateEvent(state=session.state))
        basket = await views.public_basket(db, session_id)
        if basket.lines:
            await send(BasketEvent(lines=basket.lines, total=basket.total))
        await send(AgentStateEvent(state=AgentState(state.customer_hub.last_agent_state(session_id))))
        for msg in await views.recent_transcripts(db, session_id, REPLAY_TRANSCRIPTS):
            await send(TranscriptEvent(speaker=msg.speaker, text=msg.text))
        try:
            while True:
                raw = await ws.receive_json()
                try:
                    event = customer_inbound_adapter.validate_python(raw)
                except ValidationError:
                    await send(ErrorEvent(code="INVALID_EVENT", message="Unrecognised event"))
                    continue
                if isinstance(event, TextInput):
                    lock = state.turn_locks.setdefault(session_id, asyncio.Lock())
                    async with lock:
                        await db.refresh(session)
                        if session.state in TERMINAL_STATES:
                            await send(ErrorEvent(code="WRONG_STATE", message="This session has ended"))
                            continue
                        await send(TranscriptEvent(speaker="customer", text=event.text))
                        await trace.record_message(
                            db,
                            state.merchant_hub,
                            session_id,
                            channel="customer",
                            speaker="customer",
                            text=event.text,
                        )
                        await send(AgentStateEvent(state=AgentState.thinking))
                        reply = await customer_turn(
                            db,
                            state.hubs,
                            state.llm,
                            session_id,
                            event.text,
                            pinned=state.language_pins.get(session_id),
                        )
                        await trace.record_message(
                            db,
                            state.merchant_hub,
                            session_id,
                            channel="customer",
                            speaker="hermion",
                            text=reply,
                        )
                        await send(TranscriptEvent(speaker="hermion", text=reply))
                        await send(AgentStateEvent(state=AgentState.idle))
                elif isinstance(event, LanguagePin):
                    shop = await catalog.get_merchant(db)
                    if event.code is not None and event.code not in shop.languages:
                        await send(
                            ErrorEvent(
                                code="UNSUPPORTED_LANGUAGE", message="Language is not available in this shop"
                            )
                        )
                    else:
                        state.language_pins[session_id] = event.code
                # Mute takes effect with voice streaming in Stage 3.
        except WebSocketDisconnect:
            log.info("customer socket closed")
        finally:
            state.customer_hub.remove(session_id, ws)
