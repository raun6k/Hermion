"""Dev-only helpers for the voice lane: test clip, streamed TTS, and a mic -> STT socket.

Used by the /dev/voice page to check the browser audio path without the full call pipeline.
"""

import asyncio
import contextlib
import logging

from fastapi import APIRouter, Query, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from app import languages
from app.schemas.common import AppError
from app.speech.stt import STTCallbacks, Transcript, build_stt
from app.speech.tts import SPEECH_SAMPLE_RATE, build_tts, split_sentences

log = logging.getLogger(__name__)
router = APIRouter(prefix="/dev", tags=["dev"])


def _require_language(lang: str) -> None:
    if not languages.is_supported(lang):
        raise AppError(
            "UNSUPPORTED_LANGUAGE", f"{lang} is not supported; use one of {', '.join(languages.LANGUAGES)}"
        )


@router.get("/tts-test", response_class=Response)
async def tts_test(request: Request, lang: str = Query("te-IN")) -> Response:
    """Speak the sample greeting for any supported language (see app/languages.py)."""
    _require_language(lang)
    wav = await build_tts(request.app.state.settings).synthesize(languages.LANGUAGES[lang].sample, lang)
    return Response(content=wav, media_type="audio/wav")


@router.get("/tts-stream")
async def tts_stream(
    request: Request, lang: str = Query("te-IN"), text: str = Query("")
) -> StreamingResponse:
    """Raw 16-bit mono PCM (24 kHz), streamed sentence by sentence, for the browser TtsPlayer."""
    _require_language(lang)
    spoken = text.strip() or languages.LANGUAGES[lang].sample
    pcm = build_tts(request.app.state.settings).stream(split_sentences(spoken), lang)
    return StreamingResponse(pcm, media_type=f"audio/L16;rate={SPEECH_SAMPLE_RATE};channels=1")


@router.websocket("/stt")
async def stt_socket(ws: WebSocket, lang: str = "auto") -> None:
    """Binary 16 kHz PCM frames in; JSON events out: speech_start, speech_end, partial, final, error."""
    if lang != "auto" and not languages.is_supported(lang):
        await ws.close(code=4400, reason="unsupported language")
        return
    await ws.accept()
    outbox: asyncio.Queue[dict] = asyncio.Queue()

    async def put(event: dict) -> None:
        outbox.put_nowait(event)

    async def final(t: Transcript) -> None:
        await put({"type": "final", "text": t.text, "language": t.language})

    callbacks = STTCallbacks(
        on_final=final,
        on_partial=lambda text: put({"type": "partial", "text": text}),
        on_speech_start=lambda: put({"type": "speech_start"}),
        on_speech_end=lambda: put({"type": "speech_end"}),
        on_error=lambda message: put({"type": "error", "message": message}),
    )
    try:
        session = await build_stt(ws.app.state.settings).open_stream(callbacks, lang)
    except Exception as exc:
        await ws.send_json({"type": "error", "message": f"could not open STT: {exc}"})
        await ws.close()
        return
    await ws.send_json({"type": "ready"})

    async def pump() -> None:
        while True:
            await ws.send_json(await outbox.get())

    sender = asyncio.create_task(pump())
    try:
        while True:
            message = await ws.receive()
            if message["type"] == "websocket.disconnect":
                break
            if data := message.get("bytes"):
                await session.push_pcm(data)
    except WebSocketDisconnect:
        pass
    finally:
        sender.cancel()
        with contextlib.suppress(Exception):
            await session.close()
