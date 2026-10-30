"""Tool schemas exposed to the LLM and their dispatch to services. Spec: docs/engine.md#tools.

`session_id` is injected server-side and never appears in a tool schema.
"""

from typing import Any

TOOL_NAMES = (
    "search_products",
    "evaluate_offer",
    "suggest_bundle",
    "add_to_basket",
    "remove_from_basket",
    "propose_mandate",
)


def tool_schemas(state: str) -> list[dict[str, Any]]:
    """OpenAI-format tool definitions allowed in this session state."""
    raise NotImplementedError


async def dispatch(name: str, arguments: dict[str, Any], session_id: str) -> dict[str, Any]:
    raise NotImplementedError
