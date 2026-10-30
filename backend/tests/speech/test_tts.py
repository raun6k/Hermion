"""SarvamTTS speaker lookup from SARVAM_TTS_SPEAKERS, with a fake WebSocket (no network)."""

import base64
import json
import logging

import pytest

from app.config import Settings
from app.speech import tts


class FakeSocket:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def __aenter__(self) -> "FakeSocket":
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def send(self, raw: str) -> None:
        self.sent.append(json.loads(raw))

    def __aiter__(self):
        async def messages():
            yield json.dumps(
                {"type": "audio", "data": {"audio": base64.b64encode(b"\x00\x00" * 10).decode()}}
            )
            yield json.dumps({"type": "event", "data": {"event_type": "final"}})

        return messages()

    @property
    def config(self) -> dict:
        return next(m["data"] for m in self.sent if m["type"] == "config")


@pytest.fixture
def socket(monkeypatch: pytest.MonkeyPatch) -> FakeSocket:
    sock = FakeSocket()
    monkeypatch.setattr(tts.websockets, "connect", lambda *a, **kw: sock)
    return sock


def _settings(speakers: str) -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://u:p@localhost/db",
        use_fake_llm=True,
        sarvam_api_key="test-key",
        sarvam_tts_speakers=speakers,
        _env_file=None,
    )


async def test_speaker_from_map(socket: FakeSocket) -> None:
    wav = await tts.SarvamTTS(_settings("hi-IN=aparna_hi_customer,te-IN=ravi_te_sales")).synthesize(
        "x", "te-IN"
    )
    assert wav[:4] == b"RIFF"
    assert socket.config["speaker"] == "ravi_te_sales"
    assert socket.config["language_code"] == "te-IN"


async def test_any_language_with_an_entry_works(socket: FakeSocket) -> None:
    await tts.SarvamTTS(_settings("kn-IN=anu_kn_customer")).synthesize("x", "kn-IN")
    assert socket.config["speaker"] == "anu_kn_customer"


async def test_missing_language_falls_back_to_default(
    socket: FakeSocket, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger=tts.__name__):
        await tts.SarvamTTS(_settings("hi-IN=aparna_hi_customer")).synthesize("x", "ta-IN")
    assert "speaker" not in socket.config
    assert "no SARVAM_TTS_SPEAKERS entry for ta-IN" in caplog.text
