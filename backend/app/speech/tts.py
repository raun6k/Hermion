"""Text-to-speech. Production model: bulbul:v4-flash over WebSocket (docs/voice.md#tts-bulbulv4-flash).

Walking skeleton: one-shot `synthesize` returning a WAV, used by `make smoke` and the audio test clip.
Per-sentence streaming to the customer is built in the voice lane.
"""

import base64
import io
import json
import logging
import wave
from typing import Protocol
from urllib.parse import urlencode

import websockets

from app.config import Settings
from app.speech.sarvam import AUTH_HEADER, SARVAM_WS, SarvamError, event_name, parse, payload

log = logging.getLogger(__name__)

SPEECH_SAMPLE_RATE = 24_000  # streaming maximum


class TTSClient(Protocol):
    async def synthesize(self, text: str, language_code: str, sample_rate: int = SPEECH_SAMPLE_RATE) -> bytes:
        """Return a complete WAV file."""
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

    async def synthesize(self, text: str, language_code: str, sample_rate: int = SPEECH_SAMPLE_RATE) -> bytes:
        query = urlencode({"model": self._model, "send_completion_event": "true"})
        url = f"{SARVAM_WS}/text-to-speech/ws?{query}"
        config: dict = {
            "language_code": language_code,
            "output_audio_codec": "linear16",
            "speech_sample_rate": sample_rate,
            "enable_preprocessing": True,
        }
        if speaker := self._speakers.get(language_code):
            config["speaker"] = speaker
        else:
            log.warning("no SARVAM_TTS_SPEAKERS entry for %s; using Sarvam's default voice", language_code)
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
    """Returns 0.3 s of silence."""

    async def synthesize(self, text: str, language_code: str, sample_rate: int = SPEECH_SAMPLE_RATE) -> bytes:
        return _pcm_to_wav(b"\x00\x00" * int(sample_rate * 0.3), sample_rate)


def build_tts(settings: Settings) -> TTSClient:
    return FakeTTS() if settings.use_fake_speech else SarvamTTS(settings)
