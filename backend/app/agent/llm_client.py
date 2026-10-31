"""The only module that talks to an LLM provider. Spec: docs/engine.md#llm-provider.

OpenRouter is OpenAI-compatible, so we use the OpenAI SDK with OpenRouter's base URL.
"""

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from openai import AsyncOpenAI

from app.config import Settings

log = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class LLMResponse:
    text: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    model: str = ""
    latency_ms: int = 0


class LLMError(Exception):
    pass


class LLMClient(Protocol):
    async def complete(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
    ) -> LLMResponse: ...


class OpenRouterClient:
    def __init__(self, settings: Settings) -> None:
        self._model = settings.llm_model
        self._fallbacks = settings.llm_fallback_models
        self._client = AsyncOpenAI(
            base_url=OPENROUTER_BASE_URL,
            api_key=settings.openrouter_api_key,
            timeout=settings.llm_timeout_s,
            max_retries=0,
            default_headers={"HTTP-Referer": "http://localhost:3000", "X-OpenRouter-Title": "Hermion"},
        )

    async def complete(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
    ) -> LLMResponse:
        extra_body: dict[str, Any] = {
            # Reasoning off: voice turns need a fast first token (docs/engine.md#llm-provider).
            "reasoning": {"effort": "none"},
            "provider": {"require_parameters": True, "sort": "latency", "data_collection": "deny"},
        }
        if self._fallbacks:
            extra_body["models"] = [self._model, *self._fallbacks]
        kwargs: dict[str, Any] = {"model": self._model, "messages": messages, "extra_body": extra_body}
        if tools:
            # Tools are re-sent on every request; one tool runs at a time (enforced in the agent loop,
            # since GPT-6 Luna on OpenRouter does not accept `parallel_tool_calls`).
            kwargs |= {"tools": tools, "tool_choice": "auto"}

        started = time.perf_counter()
        try:
            resp = await self._client.chat.completions.create(**kwargs)
        except Exception as exc:  # network, timeout, provider error
            raise LLMError(str(exc)) from exc
        latency_ms = int((time.perf_counter() - started) * 1000)

        if not resp.choices:
            raise LLMError("empty response")
        msg = resp.choices[0].message
        try:
            calls = [
                ToolCall(id=c.id, name=c.function.name, arguments=json.loads(c.function.arguments or "{}"))
                for c in (msg.tool_calls or [])
            ]
        except (ValueError, TypeError) as exc:
            raise LLMError("invalid tool arguments") from exc
        log.info("llm model=%s latency_ms=%d tool_calls=%d", resp.model, latency_ms, len(calls))
        return LLMResponse(
            text=msg.content, tool_calls=calls, model=resp.model or self._model, latency_ms=latency_ms
        )


class FakeLLMClient:
    """Deterministic stand-in for tests and offline dev. Replies with scripted text, else an echo."""

    def __init__(self, script: list[LLMResponse] | None = None) -> None:
        self._script = list(script or [])
        self.calls: list[list[dict[str, Any]]] = []

    async def complete(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
    ) -> LLMResponse:
        self.calls.append(messages)
        if self._script:
            return self._script.pop(0)
        last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        return LLMResponse(text=f"Namaste! I am Hermion (fake LLM). You said: {last_user}", model="fake")


def build_llm_client(settings: Settings) -> LLMClient:
    return FakeLLMClient() if settings.use_fake_llm else OpenRouterClient(settings)
