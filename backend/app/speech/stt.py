"""Speech-to-text. Production model: saaras:v3-realtime (docs/voice.md#stt-saarasv3-realtime).

Two APIs behind one client: one-shot `transcribe_pcm` (smoke test) and `open_stream`, a live session
(push 16 kHz PCM, get VAD / partial / final callbacks) that the turn pipeline uses in Stage 3.
"""

import asyncio
import base64
import contextlib
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlencode

import websockets

from app import languages
from app.config import Settings
from app.speech.sarvam import AUTH_HEADER, SARVAM_WS, SarvamError, event_name, parse, payload

log = logging.getLogger(__name__)

SAMPLE_RATE = 16_000
CHUNK_BYTES = SAMPLE_RATE * 2 // 10  # 100 ms of 16-bit mono PCM


@dataclass(frozen=True)
class Transcript:
    text: str
    language: str | None = None


Callback = Callable[..., Awaitable[None]]


@dataclass
class STTCallbacks:
    """All optional. `on_final(Transcript)`, `on_partial(str)`, `on_speech_start()`, `on_speech_end()`,
    `on_error(str)`. Barge-in (stop TTS) hangs off `on_speech_start`."""

    on_final: Callback | None = None
    on_partial: Callback | None = None
    on_speech_start: Callback | None = None
    on_speech_end: Callback | None = None
    on_error: Callback | None = None


class STTSession(Protocol):
    async def push_pcm(self, pcm: bytes) -> None:
        """16 kHz mono 16-bit PCM, any chunk size."""
        ...

    async def close(self) -> None: ...


class STTClient(Protocol):
    async def transcribe_pcm(self, pcm: bytes, language_code: str = "auto") -> Transcript: ...

    async def open_stream(self, callbacks: STTCallbacks, language_code: str = "auto") -> STTSession: ...


class SarvamRealtimeSTT:
    def __init__(self, settings: Settings, model: str = "saaras:v3-realtime", mode: str = "codemix") -> None:
        self._key, self._model, self._mode = settings.sarvam_api_key, model, mode

    def _url(self, language_code: str) -> str:
        query = {
            "model": self._model,
            "language_code": languages.to_stt_code(language_code),  # "auto" passes through
            "mode": self._mode,
            "stream_type": "fast",
            "sample_rate": SAMPLE_RATE,
            "endpointing": "vad",
            "silence_duration_ms": 900,
            "encoding": "linear16",
        }
        return f"{SARVAM_WS}/speech-to-text-realtime/ws?{urlencode(query)}"

    async def open_stream(self, callbacks: STTCallbacks, language_code: str = "auto") -> STTSession:
        """Open a live session. `language_code` pins the language ("auto" = detect per utterance)."""
        ws = await websockets.connect(
            self._url(language_code), additional_headers={AUTH_HEADER: self._key}, open_timeout=10
        )
        stream = SarvamSTTStream(ws, callbacks)
        try:
            await stream.wait_ready()
        except Exception:
            await stream.close()
            raise
        return stream

    async def transcribe_pcm(self, pcm: bytes, language_code: str = "auto") -> Transcript:
        """Send 16 kHz mono 16-bit PCM, flush, and return the final transcript."""
        texts: list[str] = []
        language = None
        events: list[str] = []
        audio = pcm + b"\x00\x00" * SAMPLE_RATE  # 1 s trailing silence so server VAD ends the utterance
        async with websockets.connect(
            self._url(language_code), additional_headers={AUTH_HEADER: self._key}, open_timeout=10
        ) as ws:

            async def read_until(*names: str) -> tuple[str, dict]:
                while True:
                    msg = parse(await asyncio.wait_for(ws.recv(), timeout=20))
                    name, data = event_name(msg), payload(msg)
                    events.append(name)
                    if name == "error":
                        raise SarvamError(f"STT error: {data}")
                    if name in names:
                        return name, data

            await read_until("session.begin")
            for i in range(0, len(audio), CHUNK_BYTES):
                chunk = base64.b64encode(audio[i : i + CHUNK_BYTES]).decode()
                await ws.send(json.dumps({"event": "audio_input", "audio": chunk}))
                await asyncio.sleep(0.02)  # ~5x real time; the server expects a stream, not a dump
            await ws.send(json.dumps({"event": "flush"}))
            # Like a live mic: keep streaming silence until the server finalises (max ~10 s).
            silence = base64.b64encode(b"\x00\x00" * (SAMPLE_RATE // 10)).decode()
            final = asyncio.ensure_future(read_until("transcript.final"))
            try:
                for _ in range(100):
                    if final.done():
                        break
                    await ws.send(json.dumps({"event": "audio_input", "audio": silence}))
                    await asyncio.wait({final}, timeout=0.1)
                if not final.done():
                    raise SarvamError(f"no transcript.final; events seen: {sorted(set(events))}")
                _, data = final.result()
            finally:
                final.cancel()
            texts.append(str(data.get("text", "")))
            detected = data.get("language")
            language = languages.from_stt_code(detected) if detected else None
            await ws.send(json.dumps({"event": "end"}))
        if not texts:
            raise SarvamError("STT closed without a final transcript")
        return Transcript(text=" ".join(t for t in texts if t).strip(), language=language)


async def _fire(cb: Callback | None, *args: object) -> None:
    if cb is not None:
        try:
            await cb(*args)
        except Exception:
            log.exception("STT callback failed")


class SarvamSTTStream:
    """Live saaras:v3-realtime session. A reader task turns server events into callbacks; a writer task
    sends queued PCM and, when the mic goes quiet, silence, because the server needs a continuous
    stream to finalise an utterance (docs/voice.md#verified-protocol-facts-smoke-2026-10-30)."""

    def __init__(self, ws, callbacks: STTCallbacks) -> None:  # noqa: ANN001
        self._ws, self._cb = ws, callbacks
        self._queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._ready = asyncio.Event()
        self._closed = False
        self._tasks = [asyncio.create_task(self._read()), asyncio.create_task(self._write())]

    async def wait_ready(self, wait_s: float = 10) -> None:
        async with asyncio.timeout(wait_s):
            await self._ready.wait()

    async def push_pcm(self, pcm: bytes) -> None:
        if self._closed:
            return
        for i in range(0, len(pcm), CHUNK_BYTES):
            self._queue.put_nowait(pcm[i : i + CHUNK_BYTES])

    async def _send_audio(self, pcm: bytes) -> None:
        await self._ws.send(json.dumps({"event": "audio_input", "audio": base64.b64encode(pcm).decode()}))

    async def _write(self) -> None:
        await self._ready.wait()
        silence = b"\x00\x00" * (SAMPLE_RATE // 10)
        try:
            while not self._closed:
                try:
                    chunk = await asyncio.wait_for(self._queue.get(), timeout=0.1)
                except TimeoutError:
                    chunk = silence
                await self._send_audio(chunk)
        except Exception as exc:
            if not self._closed:
                await _fire(self._cb.on_error, f"STT write failed: {exc}")

    async def _read(self) -> None:
        try:
            async for raw in self._ws:
                msg = parse(raw)
                name, data = event_name(msg), payload(msg)
                if name == "session.begin":
                    self._ready.set()
                elif name == "vad.speech_start":
                    await _fire(self._cb.on_speech_start)
                elif name == "vad.speech_end":
                    await _fire(self._cb.on_speech_end)
                elif name == "transcript.partial":
                    await _fire(self._cb.on_partial, str(data.get("text", "")))
                elif name == "transcript.final":
                    detected = data.get("language")
                    language = languages.from_stt_code(detected) if detected else None
                    text = str(data.get("text", "")).strip()
                    if text:
                        await _fire(self._cb.on_final, Transcript(text=text, language=language))
                elif name == "error":
                    await _fire(self._cb.on_error, f"STT error: {data}")
        except Exception as exc:
            if not self._closed:
                await _fire(self._cb.on_error, f"STT read failed: {exc}")

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        with contextlib.suppress(Exception):
            await self._ws.send(json.dumps({"event": "end"}))
        for task in self._tasks:
            task.cancel()
        with contextlib.suppress(Exception):
            await self._ws.close()


class FakeSTTSession:
    """Emits one utterance (speech_start, partial, speech_end, final) per second of non-silent PCM."""

    def __init__(self, callbacks: STTCallbacks, text: str, language: str) -> None:
        self._cb, self._text, self._language = callbacks, text, language
        self._buffered = 0
        self.received = 0

    async def push_pcm(self, pcm: bytes) -> None:
        self.received += len(pcm)
        if not any(pcm):
            return
        if self._buffered == 0:
            await _fire(self._cb.on_speech_start)
        self._buffered += len(pcm)
        if self._buffered >= SAMPLE_RATE * 2:  # 1 s
            self._buffered = 0
            await _fire(self._cb.on_partial, self._text.split(" ")[0])
            await _fire(self._cb.on_speech_end)
            await _fire(self._cb.on_final, Transcript(text=self._text, language=self._language))

    async def close(self) -> None:
        return None


class FakeSTT:
    def __init__(self, text: str = "fake transcript", language: str = "te-IN") -> None:
        self._t = Transcript(text=text, language=language)

    async def transcribe_pcm(self, pcm: bytes, language_code: str = "auto") -> Transcript:
        return self._t

    async def open_stream(self, callbacks: STTCallbacks, language_code: str = "auto") -> STTSession:
        return FakeSTTSession(callbacks, self._t.text, self._t.language or "te-IN")


def build_stt(settings: Settings) -> STTClient:
    return FakeSTT() if settings.use_fake_speech else SarvamRealtimeSTT(settings)
