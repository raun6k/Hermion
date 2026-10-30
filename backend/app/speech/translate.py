"""Async trace translation to the merchant's language (Mayura). Spec: docs/voice.md. Built in Stage 3."""

from typing import Protocol


class Translator(Protocol):
    async def translate(self, text: str, source: str | None, target: str) -> str: ...


class FakeTranslator:
    async def translate(self, text: str, source: str | None, target: str) -> str:
        return text
