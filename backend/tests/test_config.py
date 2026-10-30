import pytest
from pydantic import ValidationError

from app.config import Settings, parse_speaker_map

DB = "postgresql+asyncpg://u:p@localhost/db"


def test_missing_keys_fail_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USE_FAKE_LLM", "false")
    monkeypatch.setenv("USE_FAKE_SPEECH", "false")
    with pytest.raises(ValidationError, match="OPENROUTER_API_KEY.*SARVAM_API_KEY"):
        Settings(database_url=DB, _env_file=None)


def test_fakes_need_no_keys() -> None:
    s = Settings(database_url=DB, use_fake_llm=True, use_fake_speech=True, _env_file=None)
    assert s.llm_model == "openai/gpt-6-luna"


def test_csv_lists(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_FALLBACK_MODELS", "a/x, b/y")
    monkeypatch.setenv("CORS_ORIGINS", "http://a,http://b")
    s = Settings(database_url=DB, use_fake_llm=True, use_fake_speech=True, _env_file=None)
    assert s.llm_fallback_models == ["a/x", "b/y"]
    assert s.cors_origins == ["http://a", "http://b"]


# ---- SARVAM_TTS_SPEAKERS -------------------------------------------------------------


def test_speaker_map_valid() -> None:
    assert parse_speaker_map("hi-IN=aparna_hi_customer,te-IN=ravi_te_sales") == {
        "hi-IN": "aparna_hi_customer",
        "te-IN": "ravi_te_sales",
    }


def test_speaker_map_trims_whitespace() -> None:
    assert parse_speaker_map("  hi-IN = aparna_hi_customer ,\ten-IN=simran_en_sales  ") == {
        "hi-IN": "aparna_hi_customer",
        "en-IN": "simran_en_sales",
    }


@pytest.mark.parametrize("raw", ["", "   ", ",", " , ,"])
def test_speaker_map_empty(raw: str) -> None:
    assert parse_speaker_map(raw) == {}


def test_speaker_map_skips_empty_entries() -> None:
    assert parse_speaker_map(",hi-IN=aparna_hi_customer,,") == {"hi-IN": "aparna_hi_customer"}


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("hi-IN", "malformed entry 'hi-IN'"),
        ("hi-IN=", "malformed entry 'hi-IN='"),
        ("=aparna_hi_customer", "malformed entry"),
        ("hindi=aparna_hi_customer", "not a supported language code"),
        ("xx-IN=aparna_hi_customer", "not a supported language code"),
        ("ml-IN=some_ml_voice", "no personas for ml-IN"),
        ("hi-IN=shubh", "not a Bulbul v4 persona ID"),
    ],
)
def test_speaker_map_malformed(raw: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_speaker_map(raw)


def test_speaker_map_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SARVAM_TTS_SPEAKERS", "te-IN=ravi_te_sales")
    s = Settings(database_url=DB, use_fake_llm=True, use_fake_speech=True, _env_file=None)
    assert s.sarvam_tts_speakers == {"te-IN": "ravi_te_sales"}


def test_speaker_map_bad_env_fails_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SARVAM_TTS_SPEAKERS", "te-IN")
    with pytest.raises(ValidationError, match="SARVAM_TTS_SPEAKERS: malformed entry"):
        Settings(database_url=DB, use_fake_llm=True, use_fake_speech=True, _env_file=None)
