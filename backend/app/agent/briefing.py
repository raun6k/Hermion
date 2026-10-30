"""Merchant briefing channel: plain text -> proposed mandate. Spec: docs/engine.md#mandates."""

from typing import Any


async def handle_briefing(session_id: str, text: str) -> dict[str, Any]:
    raise NotImplementedError
