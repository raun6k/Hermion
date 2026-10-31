"""Customer socket: serialized turns, streaming speech and reconnect replay."""

import asyncio
import contextlib
import logging
import time
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app import languages
from app.agent.customer import customer_turn, generate_greeting
from app.db.models import TERMINAL_STATES, Session, SessionState
from app.db.session import sessionmaker
from app.schemas.common import AgentState
from app.schemas.events import (
    AgentStateEvent,
    BasketEvent,
    ErrorEvent,
    Mute,
    StateEvent,
    TextInput,
    TranscriptEvent,
    TtsEnd,
    TtsStop,
    UiLanguage,
    VoiceStart,
    customer_inbound_adapter,
)
from app.services import catalog, sessions, trace, views
from app.speech.stt import STTCallbacks, Transcript, build_stt
from app.speech.tts import build_tts, split_sentences
from app.speech.turn_taking import BargeInGate, endpoint_delay_ms

log = logging.getLogger(__name__)
router = APIRouter()


class TimedLLM:
    """Measure all model calls for one turn, including retries and failures."""

    def __init__(self, client):
        self.client = client
        self.seconds = 0.0
        self.calls = 0

    async def complete(self, messages, tools=None):
        started = time.perf_counter()
        self.calls += 1
        try:
            return await self.client.complete(messages, tools=tools)
        finally:
            self.seconds += time.perf_counter() - started


@router.websocket("/ws/sessions/{session_id}")
async def customer_ws(ws: WebSocket, session_id: UUID) -> None:
    state = ws.app.state
    async with sessionmaker()() as db:
        session = await db.get(Session, session_id)
        if session is None or session.state in TERMINAL_STATES:
            await ws.close(code=4404, reason="unknown or ended session")
            return
        merchant_id = session.merchant_id  # read before commits expire the row
        await ws.accept()
        state.customer_hub.set(session_id, ws)
        voice = False
        muted = False
        stream = None
        speech_end = None
        tts_task = None
        speaking = False  # the customer is mid-speech (VAD), so Hermion must not talk over them
        endpoint_task = None
        heard: list[str] = []  # finals of one spoken turn, joined once the customer has been quiet
        heard_language: str | None = None
        unspoken_greeting: tuple[str, str] | None = None  # greeted before the mic was ready
        ui_language: str | None = None
        greeting_task = None
        gate = BargeInGate()
        turn_task: asyncio.Task | None = None  # the customer_turn being generated, cancellable on barge-in
        interrupted: str | None = None  # text of a turn dropped because the customer kept talking
        deferred_speech: tuple | None = None  # a reply held back while VAD reported speech
        queue: asyncio.Queue[tuple[str, str | None, float | None, float, str]] = asyncio.Queue()

        async def send(event):
            await state.customer_hub.send(session_id, event)

        async def stop_tts():
            nonlocal tts_task
            if tts_task and not tts_task.done():
                tts_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await tts_task
            tts_task = None
            await send(TtsStop())

        async def speak(text, language, started=None, timing_id=None):
            try:
                await send(AgentStateEvent(state=AgentState.speaking))
                first = True
                async for chunk in build_tts(state.settings).stream(split_sentences(text), language):
                    if first and started is not None:
                        log.info(
                            "voice_timing session=%s speech_end_to_first_audio_ms=%d",
                            session_id,
                            int((time.perf_counter() - started) * 1000),
                        )
                        first = False
                    await ws.send_bytes(chunk)
                    if timing_id and started is not None:
                        elapsed = int((time.perf_counter() - started) * 1000)
                        task = asyncio.create_task(
                            trace.record_first_audio(state.merchant_hub, timing_id, elapsed)
                        )
                        state.merchant_hub.translation_tasks.add(task)
                        task.add_done_callback(state.merchant_hub.translation_tasks.discard)
                        timing_id = None
                await send(TtsEnd())
                await send(AgentStateEvent(state=AgentState.idle))
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("TTS failed")
                await send(
                    ErrorEvent(code="SPEECH_ERROR", message="Voice playback failed. Please try again.")
                )
                await send(AgentStateEvent(state=AgentState.idle))

        def start_speech(text, language, started=None, timing_id=None):
            nonlocal tts_task
            if voice and language:
                if tts_task and not tts_task.done():
                    tts_task.cancel()
                tts_task = asyncio.create_task(speak(text, language, started, timing_id))

        state.customer_hub.speech_callbacks[session_id] = start_speech

        async def greet_if_needed():
            """Greet once, in the customer's UI language; replies then follow whatever they speak."""
            nonlocal unspoken_greeting
            await db.refresh(session)
            if session.state != SessionState.intro:
                return
            recent = await views.recent_transcripts(db, session_id, 20)
            if any(message.speaker == "hermion" for message in recent):
                await sessions.transition(db, state.hubs, session_id, SessionState.discovery)
                return
            shop = await catalog.get_merchant(db, merchant_id)
            language = ui_language if ui_language in shop.languages else shop.languages[0]
            session.language = language
            await db.commit()
            await send(AgentStateEvent(state=AgentState.thinking))
            reply = await generate_greeting(db, state.llm, session_id, language)
            await trace.record_message(
                db,
                state.merchant_hub,
                session_id,
                channel="customer",
                speaker="hermion",
                text=reply,
                language=language,
            )
            await sessions.transition(db, state.hubs, session_id, SessionState.discovery)
            await send(TranscriptEvent(speaker="hermion", text=reply))
            if voice:
                start_speech(reply, language)
            else:  # the mic prompt may still be open: spoken when voice starts
                unspoken_greeting = (reply, language)
                await send(AgentStateEvent(state=AgentState.idle))

        async def greet_locked():
            try:
                async with state.turn_locks.setdefault(session_id, asyncio.Lock()):
                    await greet_if_needed()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("greeting failed")
                await send(ErrorEvent(code="TURN_ERROR", message="Please try again."))

        async def worker():
            nonlocal turn_task, interrupted, deferred_speech
            while True:
                text, detected, ended, finalized, input_kind = await queue.get()
                try:
                    async with (
                        state.turn_locks.setdefault(session_id, asyncio.Lock()),
                        sessionmaker()() as turn_db,
                    ):
                        current = await turn_db.get(Session, session_id)
                        if not current or current.state in TERMINAL_STATES:
                            await send(ErrorEvent(code="WRONG_STATE", message="This session has ended"))
                            continue
                        if current.state == SessionState.intro:
                            await sessions.transition(db, state.hubs, session_id, SessionState.discovery)
                        await send(TranscriptEvent(speaker="customer", text=text))
                        customer_message = await trace.record_message(
                            turn_db,
                            state.merchant_hub,
                            session_id,
                            channel="customer",
                            speaker="customer",
                            text=text,
                            language=detected,
                        )
                        await send(AgentStateEvent(state=AgentState.thinking))
                        began = time.perf_counter()
                        timed_llm = TimedLLM(state.llm)
                        turn_task = asyncio.create_task(
                            customer_turn(
                                turn_db,
                                state.hubs,
                                timed_llm,
                                session_id,
                                text,
                                stt_language=detected,
                                voice=input_kind == "voice",
                            )
                        )
                        try:
                            reply = await turn_task
                        except asyncio.CancelledError:
                            if asyncio.current_task().cancelling():
                                raise
                            # The customer kept talking: drop this reply; their next words merge into it.
                            await turn_db.rollback()
                            interrupted = text
                            await send(AgentStateEvent(state=AgentState.listening))
                            continue
                        finally:
                            turn_task = None
                        await turn_db.refresh(current)
                        log.info(
                            "turn_timing session=%s agent_ms=%d model_ms=%d model_calls=%d "
                            "stt_final_ms=%s queue_ms=%d",
                            session_id,
                            int((time.perf_counter() - began) * 1000),
                            int(timed_llm.seconds * 1000),
                            timed_llm.calls,
                            int((finalized - ended) * 1000) if ended else None,
                            int((began - finalized) * 1000),
                        )
                        timing_id = await trace.record_timing(
                            turn_db,
                            state.merchant_hub,
                            session_id,
                            customer_message.id,
                            {
                                "input": input_kind,
                                "stt_final_ms": int((finalized - ended) * 1000) if ended else None,
                                "queue_ms": int((began - finalized) * 1000),
                                "model_ms": int(timed_llm.seconds * 1000),
                                "model_calls": timed_llm.calls,
                                "agent_ms": int((time.perf_counter() - began) * 1000),
                                "speech_end_to_first_audio_ms": None,
                            },
                        )
                        await trace.record_message(
                            turn_db,
                            state.merchant_hub,
                            session_id,
                            channel="customer",
                            speaker="hermion",
                            text=reply,
                            language=current.language,
                        )
                        await send(TranscriptEvent(speaker="hermion", text=reply))
                        if not speaking:  # never talk over a customer who has started again
                            start_speech(reply, current.language, ended, timing_id)
                        elif voice:  # VAD may be noise: speak once it ends, unless they really talk
                            deferred_speech = (reply, current.language, ended, timing_id)
                        if not voice or speaking:
                            await send(AgentStateEvent(state=AgentState.idle))
                except asyncio.CancelledError:
                    raise
                except Exception:
                    log.exception("customer turn failed")
                    await send(ErrorEvent(code="TURN_ERROR", message="Please try saying that again."))
                finally:
                    queue.task_done()

        def busy() -> bool:
            return bool((tts_task and not tts_task.done()) or (turn_task and not turn_task.done()))

        async def speech_start():
            nonlocal speaking
            speaking = True
            if endpoint_task and not endpoint_task.done():
                endpoint_task.cancel()  # still talking: whatever was heard so far is not a finished turn
            gate.start(time.perf_counter())
            if not busy():  # nothing to protect from noise
                await stop_tts()
                await send(AgentStateEvent(state=AgentState.listening))

        async def partial(text):
            nonlocal deferred_speech
            if text.strip():  # live caption: the customer's words as they are heard
                await send(TranscriptEvent(speaker="customer", text=text.strip(), final=False))
            if not gate.partial(text, time.perf_counter()):
                return
            # Real words soon after VAD: an actual interruption, not noise.
            deferred_speech = None
            await stop_tts()
            if turn_task and not turn_task.done():
                turn_task.cancel()
            await send(AgentStateEvent(state=AgentState.listening))

        async def speech_finish():
            nonlocal speech_end, speaking, deferred_speech
            was_speaking = speaking
            speaking = False
            gate.end()
            speech_end = time.perf_counter()
            if was_speaking:
                schedule_turn()
                if deferred_speech and not heard:
                    start_speech(*deferred_speech)
                deferred_speech = None

        async def end_of_turn():
            nonlocal heard, heard_language, interrupted
            cfg = state.settings
            wait = endpoint_delay_ms(
                " ".join(heard),
                cfg.voice_endpoint_ms,
                cfg.voice_endpoint_short_ms,
                cfg.voice_endpoint_long_ms,
            )
            await asyncio.sleep(wait / 1000)
            if interrupted:  # the dropped turn and the continuation are one thought
                heard = [interrupted, *heard]
                interrupted = None
            text, language, heard, heard_language = " ".join(heard).strip(), heard_language, [], None
            # A lone letter or stray punctuation is noise, not a turn (and never a "yes").
            if sum(c.isalnum() for c in text) >= 2:
                await queue.put((text, language, speech_end, time.perf_counter(), "voice"))
            else:
                await send(AgentStateEvent(state=AgentState.idle))

        def schedule_turn():
            nonlocal endpoint_task
            if endpoint_task and not endpoint_task.done():
                endpoint_task.cancel()
            if heard and not speaking:
                endpoint_task = asyncio.create_task(end_of_turn())

        async def final(result: Transcript):
            nonlocal heard_language
            if result.text.strip():
                heard.append(result.text.strip())
                heard_language = result.language or heard_language
                schedule_turn()

        async def speech_error(_message):
            nonlocal voice, stream
            voice = False
            failed_stream, stream = stream, None
            if failed_stream is not None:
                asyncio.create_task(failed_stream.close())
            log.warning("STT failure: %s", _message)
            await send(
                ErrorEvent(code="SPEECH_ERROR", message="Could not hear you. Please try speaking again.")
            )

        async def open_stream():
            return await build_stt(state.settings).open_stream(
                STTCallbacks(
                    on_speech_start=speech_start,
                    on_speech_end=speech_finish,
                    on_partial=partial,
                    on_final=final,
                    on_error=speech_error,
                ),
                "auto",  # the customer may switch language at any time
            )

        await send(StateEvent(state=session.state))
        basket = await views.public_basket(db, session_id)
        if basket.lines:
            await send(BasketEvent(lines=basket.lines, total=basket.total))
        await send(AgentStateEvent(state=AgentState(state.customer_hub.last_agent_state(session_id))))
        for msg in await views.recent_transcripts(db, session_id, 20):
            await send(TranscriptEvent(speaker=msg.speaker, text=msg.text))
        worker_task = asyncio.create_task(worker())
        try:
            while True:
                message = await ws.receive()
                if message["type"] == "websocket.disconnect":
                    break
                if message.get("bytes") is not None:
                    if voice and not muted:
                        if stream is None:
                            try:
                                stream = await open_stream()
                            except Exception:
                                log.exception("STT connection failed")
                                await speech_error("connection failed")
                                voice = False
                                continue
                        await stream.push_pcm(message["bytes"])
                    continue
                try:
                    import json

                    event = customer_inbound_adapter.validate_python(json.loads(message.get("text") or "{}"))
                except (ValidationError, ValueError):
                    await send(ErrorEvent(code="INVALID_EVENT", message="Unrecognised event"))
                    continue
                if isinstance(event, VoiceStart):
                    voice = True
                    if greeting_task is None:
                        greeting_task = asyncio.create_task(greet_locked())
                    elif unspoken_greeting:
                        start_speech(*unspoken_greeting)
                        unspoken_greeting = None
                elif isinstance(event, Mute):
                    muted = event.muted
                elif isinstance(event, UiLanguage):
                    shop = await catalog.get_merchant(db, merchant_id)
                    if event.code not in shop.languages:
                        await send(
                            ErrorEvent(
                                code="UNSUPPORTED_LANGUAGE", message="Language is not available in this shop"
                            )
                        )
                    else:
                        ui_language = event.code
                        switched = False
                        async with sessionmaker()() as lang_db:  # own session: the greeting task owns `db`
                            row = await lang_db.get(Session, session_id)
                            if row and row.state not in TERMINAL_STATES:
                                # Mid-call change of screen language: Hermion switches too, and says so.
                                switched = greeting_task is not None and row.language != event.code
                                row.language = event.code  # screen language sets the session language
                                await lang_db.commit()
                                if switched:
                                    line = languages.require(event.code).switched
                                    await trace.record_message(
                                        lang_db,
                                        state.merchant_hub,
                                        session_id,
                                        channel="customer",
                                        speaker="hermion",
                                        text=line,
                                        language=event.code,
                                    )
                                    await send(TranscriptEvent(speaker="hermion", text=line))
                                    if not speaking:
                                        start_speech(line, event.code)
                        if greeting_task is None:
                            greeting_task = asyncio.create_task(greet_locked())
                elif isinstance(event, TextInput):
                    unspoken_greeting = None
                    if greeting_task is None:
                        greeting_task = asyncio.create_task(greet_locked())
                    await queue.put((event.text, None, None, time.perf_counter(), "text"))
        except WebSocketDisconnect:
            pass
        finally:
            background = [t for t in (worker_task, tts_task, greeting_task, endpoint_task) if t]
            for task in background:
                task.cancel()
            await asyncio.gather(*background, return_exceptions=True)
            if stream:
                await stream.close()
            if state.customer_hub.speech_callbacks.get(session_id) is start_speech:
                state.customer_hub.speech_callbacks.pop(session_id, None)
            state.customer_hub.remove(session_id, ws)
