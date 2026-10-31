"""Text-to-speech. Production model: bulbul:v4-flash over WebSocket (docs/voice.md#tts-bulbulv4-flash).

`synthesize` returns a whole WAV (smoke test, audio test clip). `stream` yields raw PCM chunks
sentence by sentence for the customer call: the first sentence is audible while the rest synthesize.
"""

import base64
import io
import json
import logging
import re
import wave
from collections.abc import AsyncIterator, Iterable
from typing import Protocol
from urllib.parse import urlencode

import websockets

from app.config import Settings
from app.speech.sarvam import AUTH_HEADER, SARVAM_WS, SarvamError, event_name, parse, payload

log = logging.getLogger(__name__)

SPEECH_SAMPLE_RATE = 24_000  # streaming maximum


MAX_REQUEST_CHARS = 2000  # Sarvam allows ~2,500 per request
_SENTENCE_END = re.compile(r"(?<=[.!?।॥])\s+")


def split_sentences(text: str) -> list[str]:
    """Split a reply into speakable sentences. Splits only where the punctuation is followed by
    whitespace, so "₹850.00" and "1,100." stay whole; over-long sentences are cut at word borders."""
    out: list[str] = []
    for part in _SENTENCE_END.split(text.strip()):
        part = part.strip()
        while len(part) > MAX_REQUEST_CHARS:
            cut = part.rfind(" ", 0, MAX_REQUEST_CHARS) or MAX_REQUEST_CHARS
            out.append(part[:cut].strip())
            part = part[cut:].strip()
        if part:
            out.append(part)
    return out


class TTSClient(Protocol):
    async def synthesize(self, text: str, language_code: str, sample_rate: int = SPEECH_SAMPLE_RATE) -> bytes:
        """Return a complete WAV file."""
        ...

    def stream(self, sentences: Iterable[str], language_code: str) -> AsyncIterator[bytes]:
        """Yield raw 16-bit mono PCM at SPEECH_SAMPLE_RATE, one sentence after another."""
        ...


def _pcm_to_wav(pcm: bytes, sample_rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    return buf.getvalue()


class SarvamTTS:
    def __init__(self, settings: Settings, model: str = "bulbul:v4-flash") -> None:
        self._key, self._model = settings.sarvam_api_key, model
        self._speakers = dict(settings.sarvam_tts_speakers)
        self._pace = settings.sarvam_tts_pace

    def _config(self, language_code: str, sample_rate: int) -> dict:
        config: dict = {
            "language_code": language_code,
            "output_audio_codec": "linear16",
            "speech_sample_rate": sample_rate,
            "enable_preprocessing": True,
            "pace": self._pace,
        }
        if speaker := self._speakers.get(language_code):
            config["speaker"] = speaker
        else:
            log.warning("no SARVAM_TTS_SPEAKERS entry for %s; using Sarvam's default voice", language_code)
        return config

    def _url(self) -> str:
        query = urlencode({"model": self._model, "send_completion_event": "true"})
        return f"{SARVAM_WS}/text-to-speech/ws?{query}"

    async def stream(self, sentences: Iterable[str], language_code: str) -> AsyncIterator[bytes]:
        """One connection per reply; each sentence is flushed on its own so audio starts after the first."""
        config = self._config(language_code, SPEECH_SAMPLE_RATE)
        async with websockets.connect(
            self._url(), additional_headers={AUTH_HEADER: self._key}, open_timeout=10
        ) as ws:
            await ws.send(json.dumps({"type": "config", "data": config}))
            for sentence in sentences:
                await ws.send(json.dumps({"type": "text", "data": {"text": sentence}}))
                await ws.send(json.dumps({"type": "flush"}))
                async for raw in ws:
                    msg = parse(raw)
                    name, data = event_name(msg), payload(msg)
                    if name == "audio":
                        yield base64.b64decode(data["audio"])
                    elif name == "error":
                        raise SarvamError(f"TTS error: {data}")
                    elif name == "event" and data.get("event_type") == "final":
                        break

    async def synthesize(self, text: str, language_code: str, sample_rate: int = SPEECH_SAMPLE_RATE) -> bytes:
        url = self._url()
        config = self._config(language_code, sample_rate)
        pcm = bytearray()
        async with websockets.connect(
            url, additional_headers={AUTH_HEADER: self._key}, open_timeout=10
        ) as ws:
            await ws.send(json.dumps({"type": "config", "data": config}))
            await ws.send(json.dumps({"type": "text", "data": {"text": text}}))
            await ws.send(json.dumps({"type": "flush"}))
            async for raw in ws:
                msg = parse(raw)
                name, data = event_name(msg), payload(msg)
                if name == "audio":
                    pcm += base64.b64decode(data["audio"])
                elif name == "error":
                    raise SarvamError(f"TTS error: {data}")
                elif name == "event" and data.get("event_type") == "final":
                    break
        if not pcm:
            raise SarvamError("TTS returned no audio")
        return _pcm_to_wav(bytes(pcm), sample_rate)


class FakeTTS:
    """Offline: 0.3 s of silence per request; `stream` yields three 100 ms chunks per sentence."""

    async def stream(self, sentences: Iterable[str], language_code: str) -> AsyncIterator[bytes]:
        for _ in sentences:
            for _ in range(3):
                yield b"\x00\x00" * (SPEECH_SAMPLE_RATE // 10)

    async def synthesize(self, text: str, language_code: str, sample_rate: int = SPEECH_SAMPLE_RATE) -> bytes:
        return _pcm_to_wav(b"\x00\x00" * int(sample_rate * 0.3), sample_rate)


def build_tts(settings: Settings) -> TTSClient:
    return FakeTTS() if settings.use_fake_speech else SarvamTTS(settings)
