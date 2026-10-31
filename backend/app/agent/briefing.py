"""Merchant briefing channel: plain text -> proposed mandate. Spec: docs/engine.md#mandates.

Prompt and argument parsing live here; the turn loop that runs it is Stage 2 (`handle_briefing`).
"""

from typing import Any
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import languages
from app.agent.guard import extract_amounts
from app.agent.language import matches_language_script
from app.agent.llm_client import LLMClient
from app.agent.loop import run_tool_loop
from app.agent.prompt import BasketLineView, StateView, build_state_block
from app.agent.tools import ToolContext, dispatch, tool_schemas
from app.db.models import Mandate, Message, SessionState
from app.schemas.merchant import BriefingResponse
from app.services import catalog, sessions, trace, views
from app.services.hub import Hubs
from app.services.mandates import MandateArgs

BRIEFING_RULES = """\
You are Hermion, the shop's sales assistant, in a private chat with the shopkeeper of {shop_name}. A customer's basket is waiting for the shopkeeper's decision and they want to guide how you negotiate it.

- Turn the shopkeeper's instruction into pricing rules by calling propose_mandate. Use search_products to find exact product_ids first.
- A rule is "settle at this price per piece" for a product, optionally only when a minimum quantity or another product is bought too. Several rules can form one deal (a pair price).
- Use the exact product ID already in the basket when the shopkeeper refers to that item. Never substitute another size or colour. For other products, match the stated colour and size, not merely the first search result. Only call propose_mandate when the instruction is clear; if a variant, price or condition is ambiguous, ask one short question instead.
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


async def handle_briefing(
    db: AsyncSession, hubs: Hubs, llm: LLMClient, session_id: UUID, text: str
) -> BriefingResponse:
    session = await sessions.get_session(db, session_id)
    sessions.require_state(session, SessionState.briefing)
    merchant = await catalog.get_merchant(db)
    await trace.record_message(
        db, hubs.merchant, session_id, channel="briefing", speaker="merchant", text=text
    )
    rows = list(
        await db.scalars(
            select(Message)
            .where(Message.session_id == session_id, Message.channel == "briefing")
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(10)
        )
    )
    rows.reverse()
    basket = await views.public_basket(db, session_id)
    merchant_language = merchant.languages[0] if merchant.languages else None
    language_name = (
        languages.require(merchant_language).name if merchant_language else "the shopkeeper's language"
    )
    messages = [
        {"role": "system", "content": build_briefing_prompt(merchant.shop_name, language_name)},
        {
            "role": "system",
            "content": briefing_state_block(
                tuple(
                    BasketLineView(
                        f"{x.product_name} (product ID {x.product_id})", x.qty, str(int(x.line_total))
                    )
                    for x in basket.lines
                ),
                None,
                merchant_language,
            ),
        },
        *[{"role": "user" if m.speaker == "merchant" else "assistant", "content": m.text} for m in rows],
    ]
    products = await catalog.list_products(db)
    allowed = {p.listed_price for p in products}
    allowed.update(extract_amounts(" ".join(m.text for m in rows if m.speaker == "merchant")))
    allowed.update(line.line_total for line in basket.lines)
    allowed.add(basket.total)
    proposed_id = None

    async def execute(name, arguments):
        nonlocal proposed_id
        result = await dispatch(ToolContext(db, hubs, session_id), name, arguments)
        await trace.record_tool_call(db, hubs.merchant, session_id, "briefing", name, arguments, result)
        if name == "propose_mandate" and "mandate_id" in result:
            proposed_id = UUID(result["mandate_id"])
        return result

    reply = await run_tool_loop(
        llm,
        messages,
        tool_schemas(SessionState.briefing),
        execute,
        lambda: allowed,
        fallback=languages.require(merchant_language).retry
        if merchant_language
        else "Sorry, could you say that again?",
        valid=lambda value: matches_language_script(value, merchant_language),
    )
    await trace.record_message(
        db, hubs.merchant, session_id, channel="briefing", speaker="hermion", text=reply
    )
    mandate = await db.get(Mandate, proposed_id) if proposed_id else None
    return BriefingResponse(
        reply=reply, proposed_mandate=views.mandate_proposal(mandate) if mandate else None
    )
