"""Customer WebSocket /ws/sessions/{id} (docs/api.md#websocket-customer-wssessionsid).

Walking skeleton: keypad text -> one LLM call -> transcript back; both messages traced.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.agent.loop import run_turn
from app.db.models import TERMINAL_STATES, Session
from app.db.session import sessionmaker
from app.log import session_id as session_id_ctx
from app.schemas.common import AgentState
from app.schemas.events import (
    AgentStateEvent,
    ErrorEvent,
    StateEvent,
    TextInput,
    TranscriptEvent,
    customer_inbound_adapter,
)
from app.services import trace

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
            await ws.send_json(event.model_dump(mode="json"))

        await send(StateEvent(state=session.state))
        await send(AgentStateEvent(state=AgentState.idle))
        try:
            while True:
                raw = await ws.receive_json()
                try:
                    event = customer_inbound_adapter.validate_python(raw)
                except ValidationError:
                    await send(ErrorEvent(code="INVALID_EVENT", message="Unrecognised event"))
                    continue
                if isinstance(event, TextInput):
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
                    reply = await run_turn(state.llm, event.text)
                    await trace.record_message(
                        db, state.merchant_hub, session_id, channel="customer", speaker="hermion", text=reply
                    )
                    await send(TranscriptEvent(speaker="hermion", text=reply))
                    await send(AgentStateEvent(state=AgentState.idle))
                # mute / language: accepted, no behaviour until the voice lane.
        except WebSocketDisconnect:
            log.info("customer socket closed")
        finally:
            state.customer_hub.remove(session_id, ws)
