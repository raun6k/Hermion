"""Settings loaded from the environment (and the repo-root `.env`). Fails fast on missing required values."""

import re
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app import languages

REPO_ROOT = Path(__file__).resolve().parents[2]


_PERSONA = re.compile(r"^[a-z0-9]+(_[a-z0-9]+){2,}$")  # v4 voice_language_style, e.g. aparna_hi_customer


def parse_speaker_map(raw: str) -> dict[str, str]:
    """Parse `SARVAM_TTS_SPEAKERS` ("hi-IN=aparna_hi_customer, te-IN=...") into {language: persona}."""
    speakers: dict[str, str] = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        language, sep, persona = (part.strip() for part in entry.partition("="))
        if not sep or not language or not persona:
            raise ValueError(f"SARVAM_TTS_SPEAKERS: malformed entry {entry!r}, expected language=persona_id")
        if not languages.is_supported(language):
            raise ValueError(
                f"SARVAM_TTS_SPEAKERS: {language!r} is not a supported language code "
                f"({', '.join(languages.LANGUAGES)}; see docs/voice.md#languages)"
            )
        if not languages.LANGUAGES[language].has_v4_voice:
            raise ValueError(f"SARVAM_TTS_SPEAKERS: bulbul:v4-flash has no personas for {language} (Q18)")
        if not _PERSONA.match(persona):
            raise ValueError(
                f"SARVAM_TTS_SPEAKERS: {persona!r} is not a Bulbul v4 persona ID (voice_language_style, "
                "e.g. aparna_hi_customer); v3 names like 'shubh' are rejected by bulbul:v4-flash"
            )
        speakers[language] = persona
    return speakers


class DatabaseSettings(BaseSettings):
    """Only what DB tooling (migrations, seed) needs; no API keys required."""

    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str = Field(description="postgresql+asyncpg://user:pass@host:port/db")


class Settings(DatabaseSettings):
    # LLM via OpenRouter (docs/engine.md#llm-provider)
    openrouter_api_key: str = ""
    llm_model: str = "openai/gpt-6-luna"
    llm_fallback_models: Annotated[list[str], NoDecode] = []
    llm_timeout_s: float = 8.0
    use_fake_llm: bool = False

    # Sarvam speech (docs/voice.md)
    sarvam_api_key: str = ""
    # Language -> Bulbul v4 persona from SARVAM_TTS_SPEAKERS ("hi-IN=aparna_hi_customer,te-IN=<id>").
    # A language with no entry uses Sarvam's default voice.
    sarvam_tts_speakers: Annotated[dict[str, str], NoDecode] = {}
    use_fake_speech: bool = False
    # Speaking rate for every voice (Bulbul v4 accepts 0.5-2.0; 1.0 is default, below is slower).
    sarvam_tts_pace: float = Field(default=0.9, ge=0.5, le=2.0)
    # The shopkeeper's own language: target of the merchant-side translation and the briefing chat.
    # There is no per-shop setting; the shop serves every language in app/languages.py.
    merchant_language: str = "en-IN"
    # Quiet time after the customer's last words before Hermion answers; shorter pauses are the same turn.
    # 0 disables waiting. The wait adapts: long after an unfinished clause, short after a full sentence.
    voice_endpoint_ms: int = Field(default=1600, ge=0, le=10_000)
    voice_endpoint_short_ms: int = Field(default=1200, ge=0, le=10_000)
    voice_endpoint_long_ms: int = Field(default=2200, ge=0, le=10_000)

    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000", "http://localhost:3001"]
    log_level: str = "INFO"

    @model_validator(mode="before")
    @classmethod
    def _split_csv(cls, data: dict) -> dict:
        for key in ("llm_fallback_models", "cors_origins"):
            for k in (key, key.upper()):
                if isinstance(data.get(k), str):
                    data[k] = [v.strip() for v in data[k].split(",") if v.strip()]
        for k in ("sarvam_tts_speakers", "SARVAM_TTS_SPEAKERS"):
            if isinstance(data.get(k), str):
                data[k] = parse_speaker_map(data[k])
        return data

    @model_validator(mode="after")
    def _known_merchant_language(self) -> "Settings":
        languages.require(self.merchant_language)
        return self

    @model_validator(mode="after")
    def _require_keys(self) -> "Settings":
        missing = []
        if not self.use_fake_llm and not self.openrouter_api_key:
            missing.append("OPENROUTER_API_KEY (or set USE_FAKE_LLM=true)")
        if not self.use_fake_speech and not self.sarvam_api_key:
            missing.append("SARVAM_API_KEY (or set USE_FAKE_SPEECH=true)")
        if missing:
            raise ValueError("Missing required settings: " + ", ".join(missing))
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
