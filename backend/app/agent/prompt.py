"""System prompt and state block builder. Spec: docs/engine.md#prompt."""

from typing import Any


def build_system_prompt(merchant: Any, state: str) -> str:
    raise NotImplementedError


def build_state_block(session: Any) -> str:
    raise NotImplementedError
