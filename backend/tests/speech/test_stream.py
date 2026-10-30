"""Streaming STT session (fake socket + fake mode), per-sentence TTS stream, Mayura translator."""

import asyncio
import base64
import json

import httpx
import pytest

from app.config import Settings
from app.speech import stt, translate, tts


def test_split_sentences() -> None:
    assert tts.split_sentences("Namaste. The shirt is ₹850.00! Shall I add it?") == [
        "Namaste.",
        "The shirt is ₹850.00!",
        "Shall I add it?",
    ]
    assert tts.split_sentences("నమస్కారం. మీకు ఏమి కావాలి?") == ["నమస్కారం.", "మీకు ఏమి కావాలి?"]
    assert tts.split_sentences("आपका स्वागत है। शर्ट ₹1,100 की है।") == ["आपका स्वागत है।", "शर्ट ₹1,100 की है।"]
    assert tts.split_sentences("  ") == []
    long = ("word " * 1000).strip()
    parts = tts.split_sentences(long)
    assert len(parts) > 1 and all(len(p) <= tts.MAX_REQUEST_CHARS for p in parts)


async def test_fake_tts_streams_chunks_per_sentence() -> None:
    chunks = [c async for c in tts.FakeTTS().stream(["a.", "b."], "te-IN")]
    assert len(chunks) == 6 and all(len(c) == tts.SPEECH_SAMPLE_RATE // 10 * 2 for c in chunks)


class FakeTtsSocket:
    def __init__(self) -> None:
        self.sent: list[dict] = []
        self._pending = 0

    async def __aenter__(self) -> "FakeTtsSocket":
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def send(self, raw: str) -> None:
        msg = json.loads(raw)
        self.sent.append(msg)
        if msg["type"] == "flush":
            self._pending += 1

    def __aiter__(self):
        async def messages():
            while self._pending:
                self._pending -= 1
                yield json.dumps(
                    {"type": "audio", "data": {"audio": base64.b64encode(b"\x01\x00" * 5).decode()}}
                )
                yield json.dumps({"type": "event", "data": {"event_type": "final"}})

        return messages()


async def test_sarvam_tts_flushes_each_sentence(monkeypatch: pytest.MonkeyPatch) -> None:
    sock = FakeTtsSocket()
    monkeypatch.setattr(tts.websockets, "connect", lambda *a, **kw: sock)
    settings = Settings(
        database_url="postgresql+asyncpg://u:p@localhost/db",
        use_fake_llm=True,
        sarvam_api_key="k",
        sarvam_tts_speakers="te-IN=pooja_te_conversation",
        _env_file=None,
    )
    out = [c async for c in tts.SarvamTTS(settings).stream(["one.", "two."], "te-IN")]
    assert len(out) == 2
    kinds = [m["type"] for m in sock.sent]
    assert kinds == ["config", "text", "flush", "text", "flush"]
    assert sock.sent[0]["data"]["speaker"] == "pooja_te_conversation"
    assert sock.sent[0]["data"]["output_audio_codec"] == "linear16"


# ---- STT -------------------------------------------------------------------------


class ScriptedSttSocket:
    """Server side of a saaras:v3-realtime session: begins, then emits scripted events after audio arrives."""

    def __init__(self, script: list[dict]) -> None:
        self.script, self.sent = script, []
        self._events: asyncio.Queue = asyncio.Queue()
        self._events.put_nowait({"event": "session.begin"})
        self.closed = False

    async def send(self, raw: str) -> None:
        msg = json.loads(raw)
        self.sent.append(msg)
        if msg["event"] == "audio_input" and self.script:
            self._events.put_nowait(self.script.pop(0))

    async def close(self) -> None:
        self.closed = True

    def __aiter__(self):
        async def messages():
            while True:
                yield json.dumps(await self._events.get())

        return messages()


async def test_stt_stream_dispatches_callbacks(monkeypatch: pytest.MonkeyPatch) -> None:
    sock = ScriptedSttSocket(
        [
            {"event": "vad.speech_start"},
            {"event": "transcript.partial", "text": "naaku"},
            {"event": "vad.speech_end"},
            {"event": "transcript.final", "text": "naaku shirt kavali", "language": "te-IN"},
        ]
    )

    async def connect(url: str, **kw):
        connect.url = url
        return sock

    monkeypatch.setattr(stt.websockets, "connect", connect)
    seen: list = []

    async def rec(kind: str, *args) -> None:
        seen.append((kind, *args))

    cb = stt.STTCallbacks(
        on_final=lambda t: rec("final", t.text, t.language),
        on_partial=lambda t: rec("partial", t),
        on_speech_start=lambda: rec("start"),
        on_speech_end=lambda: rec("end"),
    )
    settings = Settings(
        database_url="postgresql+asyncpg://u:p@localhost/db",
        use_fake_llm=True,
        sarvam_api_key="k",
        _env_file=None,
    )
    session = await stt.SarvamRealtimeSTT(settings).open_stream(cb, "od-IN")
    assert "language_code=or-IN" in connect.url  # Odia spelled the way the realtime endpoint wants it
    for _ in range(4):
        await session.push_pcm(b"\x01\x00" * 800)
    await asyncio.sleep(0.4)
    await session.close()
    assert seen == [("start",), ("partial", "naaku"), ("end",), ("final", "naaku shirt kavali", "te-IN")]
    assert any(m["event"] == "audio_input" for m in sock.sent) and sock.sent[-1] == {"event": "end"}
    assert sock.closed


async def test_stt_stream_keeps_sending_silence_when_the_mic_is_quiet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sock = ScriptedSttSocket([])

    async def connect(url: str, **kw):
        return sock

    monkeypatch.setattr(stt.websockets, "connect", connect)
    settings = Settings(
        database_url="postgresql+asyncpg://u:p@localhost/db",
        use_fake_llm=True,
        sarvam_api_key="k",
        _env_file=None,
    )
    session = await stt.SarvamRealtimeSTT(settings).open_stream(stt.STTCallbacks(), "auto")
    await asyncio.sleep(0.45)
    await session.close()
    audio = [m for m in sock.sent if m["event"] == "audio_input"]
    assert len(audio) >= 3 and not any(base64.b64decode(m["audio"]).strip(b"\x00") for m in audio)


async def test_fake_stt_stream_emits_an_utterance_per_second_of_speech() -> None:
    seen: list[str] = []

    async def rec(kind: str, *args) -> None:
        seen.append(kind)

    cb = stt.STTCallbacks(
        on_final=lambda t: rec(f"final:{t.language}"),
        on_speech_start=lambda: rec("start"),
        on_speech_end=lambda: rec("end"),
        on_partial=lambda t: rec("partial"),
    )
    session = await stt.FakeSTT(language="te-IN").open_stream(cb)
    await session.push_pcm(b"\x00\x00" * 16000)  # silence: nothing
    assert seen == []
    for _ in range(10):
        await session.push_pcm(b"\x01\x00" * 1600)
    assert seen == ["start", "partial", "end", "final:te-IN"]


# ---- translation -----------------------------------------------------------------


async def test_translator_calls_mayura_and_skips_same_language() -> None:
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        assert request.headers["api-subscription-key"] == "k"
        return httpx.Response(200, json={"translated_text": "शर्ट 850 रुपये का है।"})

    settings = Settings(
        database_url="postgresql+asyncpg://u:p@localhost/db",
        use_fake_llm=True,
        sarvam_api_key="k",
        _env_file=None,
    )
    t = translate.SarvamTranslator(settings, httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert await t.translate("The shirt is 850 rupees.", "en-IN", "hi-IN") == "शर्ट 850 रुपये का है।"
    assert calls[0]["model"] == "mayura:v1" and calls[0]["source_language_code"] == "en-IN"
    assert await t.translate("x", None, "hi-IN") == "शर्ट 850 रुपये का है।"
    assert calls[1]["source_language_code"] == "auto"
    assert await t.translate("नमस्ते", "hi-IN", "hi-IN") == "नमस्ते" and len(calls) == 2
    with pytest.raises(ValueError):
        await t.translate("x", None, "fr-FR")
