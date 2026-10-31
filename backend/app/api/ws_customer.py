"""Customer WebSocket /ws/sessions/{id} (docs/api.md#websocket-customer-wssessionsid).

Integration seam (lane B owns it). Connect replays state, basket, agent_state and the last 20 transcripts.
The customer selects a language, receives a greeting, and then sends text turns.
"""

import asyncio
import logging
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.agent.customer import customer_turn, generate_greeting
from app.db.models import TERMINAL_STATES, Session, SessionState
from app.db.session import sessionmaker
from app.log import session_id as session_id_ctx
from app.schemas.common import AgentState
from app.schemas.events import (
    AgentStateEvent,
    BasketEvent,
    ErrorEvent,
    LanguagePin,
    LanguageSelectedEvent,
    LanguageSelection,
    StateEvent,
    TextInput,
    TranscriptEvent,
    customer_inbound_adapter,
)
from app.services import catalog, sessions, trace, views

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
        if session.language:
            state.language_pins.setdefault(session_id, session.language)
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

        async def greet_if_needed() -> None:
            await db.refresh(session)
            if session.state != SessionState.intro or not session.language:
                return
            recent = await views.recent_transcripts(db, session_id, REPLAY_TRANSCRIPTS)
            if any(message.speaker == "hermion" for message in recent):
                await sessions.transition(db, state.hubs, session_id, SessionState.discovery)
                return
            await send(AgentStateEvent(state=AgentState.thinking))
            reply = await generate_greeting(db, state.llm, session_id, session.language)
            await trace.record_message(
                db,
                state.merchant_hub,
                session_id,
                channel="customer",
                speaker="hermion",
                text=reply,
                language=session.language,
            )
            await sessions.transition(db, state.hubs, session_id, SessionState.discovery)
            await send(TranscriptEvent(speaker="hermion", text=reply))
            await send(AgentStateEvent(state=AgentState.idle))

        try:
            if session.state == SessionState.intro and session.language:
                async with state.turn_locks.setdefault(session_id, asyncio.Lock()):
                    await greet_if_needed()
            while True:
                raw = await ws.receive_json()
                try:
                    event = customer_inbound_adapter.validate_python(raw)
                except ValidationError:
                    await send(ErrorEvent(code="INVALID_EVENT", message="Unrecognised event"))
                    continue
                if isinstance(event, LanguageSelection):
                    async with state.turn_locks.setdefault(session_id, asyncio.Lock()):
                        await db.refresh(session)
                        shop = await catalog.get_merchant(db)
                        if event.code not in shop.languages:
                            await send(
                                ErrorEvent(
                                    code="UNSUPPORTED_LANGUAGE",
                                    message="Language is not available in this shop",
                                )
                            )
                        elif session.state != SessionState.intro:
                            if session.language == event.code:
                                await send(LanguageSelectedEvent(code=event.code))
                            else:
                                await send(
                                    ErrorEvent(
                                        code="WRONG_STATE", message="Language selection is already complete"
                                    )
                                )
                        else:
                            session.language = event.code
                            state.language_pins[session_id] = event.code
                            await db.commit()
                            await send(LanguageSelectedEvent(code=event.code))
                            await greet_if_needed()
                elif isinstance(event, TextInput):
                    lock = state.turn_locks.setdefault(session_id, asyncio.Lock())
                    async with lock:
                        await db.refresh(session)
                        if session.state in TERMINAL_STATES:
                            await send(ErrorEvent(code="WRONG_STATE", message="This session has ended"))
                            continue
                        if session.state == SessionState.intro:
                            await send(
                                ErrorEvent(
                                    code="LANGUAGE_REQUIRED", message="Choose a language before starting"
                                )
                            )
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
