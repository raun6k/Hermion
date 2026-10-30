"""Async trace translation to the merchant's language (Mayura). Spec: docs/voice.md."""

import logging
from typing import Protocol

import httpx

from app import languages
from app.config import Settings
from app.speech.sarvam import AUTH_HEADER, SarvamError

log = logging.getLogger(__name__)

TRANSLATE_URL = "https://api.sarvam.ai/translate"
MODEL = "mayura:v1"  # covers every language in app/languages.py
MAX_CHARS = 1000  # per request


class Translator(Protocol):
    async def translate(self, text: str, source: str | None, target: str) -> str: ...


class SarvamTranslator:
    """Mayura over REST. `source=None` auto-detects. Same-language text is returned untouched."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._key = settings.sarvam_api_key
        self._client = client

    async def translate(self, text: str, source: str | None, target: str) -> str:
        languages.require(target)
        text = text.strip()
        if not text or source == target:
            return text
        body = {
            "input": text[:MAX_CHARS],
            "source_language_code": source if source and languages.is_supported(source) else "auto",
            "target_language_code": target,
            "model": MODEL,
            "mode": "formal",
            "enable_preprocessing": True,  # reads "₹850" and digits correctly
        }
        client = self._client or httpx.AsyncClient(timeout=10)
        try:
            r = await client.post(TRANSLATE_URL, json=body, headers={AUTH_HEADER: self._key})
        finally:
            if self._client is None:
                await client.aclose()
        if r.status_code != 200:
            raise SarvamError(f"translate failed: HTTP {r.status_code} {r.text[:200]}")
        return str(r.json()["translated_text"])


class FakeTranslator:
    """Offline: tags the text with the target language so tests can see it ran."""

    async def translate(self, text: str, source: str | None, target: str) -> str:
        return text if source == target else f"[{target}] {text}"


def build_translator(settings: Settings) -> Translator:
    return FakeTranslator() if settings.use_fake_speech else SarvamTranslator(settings)
