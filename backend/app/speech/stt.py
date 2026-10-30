"""Speech-to-text. Production model: saaras:v3-realtime (docs/voice.md#stt-saarasv3-realtime).

Walking skeleton: one-shot `transcribe_pcm` used by `make smoke`. Streaming into the turn
pipeline (VAD events, partials, barge-in) is built in the voice lane.
"""

import asyncio
import base64
import json
import logging
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


class STTClient(Protocol):
    async def transcribe_pcm(self, pcm: bytes, language_code: str = "auto") -> Transcript: ...


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
            "encoding": "linear16",
        }
        return f"{SARVAM_WS}/speech-to-text-realtime/ws?{urlencode(query)}"

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


class FakeSTT:
    def __init__(self, text: str = "fake transcript", language: str = "te-IN") -> None:
        self._t = Transcript(text=text, language=language)

    async def transcribe_pcm(self, pcm: bytes, language_code: str = "auto") -> Transcript:
        return self._t


def build_stt(settings: Settings) -> STTClient:
    return FakeSTT() if settings.use_fake_speech else SarvamRealtimeSTT(settings)
