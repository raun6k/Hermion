"""Merchant briefing channel: plain text -> proposed mandate. Spec: docs/engine.md#mandates.

Prompt and argument parsing live here; the turn loop that runs it is Stage 2 (`handle_briefing`).
"""

from typing import Any

from pydantic import ValidationError

from app.agent.prompt import BasketLineView, StateView, build_state_block
from app.services.mandates import MandateArgs

BRIEFING_RULES = """\
You are Hermion, the shop's sales assistant, in a private chat with the shopkeeper of {shop_name}. A customer's basket is waiting for the shopkeeper's decision and they want to guide how you negotiate it.

- Turn the shopkeeper's instruction into pricing rules by calling propose_mandate. Use search_products to find exact product_ids first.
- A rule is "settle at this price per piece" for a product, optionally only when a minimum quantity or another product is bought too. Several rules can form one deal (a pair price).
- Only call propose_mandate when the instruction is clear. If a product, price or condition is ambiguous, ask one short question instead.
- Repeat back the proposed rules briefly after the tool returns and tell the shopkeeper to confirm the card; nothing applies until they do.
- If the shopkeeper asks for a price below what the catalog allows, say it is below the shop's catalog limit and that they can change it in the catalog. The tool tells you which products were limited; never state limits or costs yourself.
- Never invent products or prices. Keep replies to one or two short sentences, written in {language}."""


def build_briefing_prompt(shop_name: str, language_name: str) -> str:
    return BRIEFING_RULES.format(shop_name=shop_name, language=language_name)


def briefing_state_block(
    basket: tuple[BasketLineView, ...], mandate: str | None, language: str | None
) -> str:
    return build_state_block(StateView(state="briefing", language=language, basket=basket, mandate=mandate))


def parse_mandate_arguments(arguments: dict[str, Any]) -> MandateArgs | None:
    """Validate `propose_mandate` arguments; None when the model produced something unusable."""
    try:
        return MandateArgs.model_validate(arguments)
    except ValidationError:
        return None


async def handle_briefing(session_id: str, text: str) -> dict[str, Any]:
    raise NotImplementedError("Stage 2: briefing turn loop (docs/build-plan.md)")
