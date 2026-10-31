"""Build a customer turn from public session data and dispatch engine-backed tools."""

import json
import re
import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import languages
from app.agent.guard import GuardFacts, allowed_amounts, extract_amounts
from app.agent.language import matches_language_script, resolve_turn_language
from app.agent.llm_client import LLMClient
from app.agent.loop import run_tool_loop
from app.agent.prompt import (
    BasketLineView,
    DecisionView,
    ShopFacts,
    StateView,
    build_state_block,
    build_system_prompt,
)
from app.agent.tools import ToolContext, dispatch, tool_schemas
from app.db.models import Goal, Message, Offer, Product, SessionState, ToolCallTrace
from app.services import catalog, sessions, trace, views
from app.services.hub import Hubs


async def generate_greeting(
    db: AsyncSession, llm: LLMClient, sid: uuid.UUID, language: str, on_fallback=None
) -> str:
    """Generate an introduction in the selected language without fabricating customer text."""
    session = await sessions.get_session(db, sid)
    merchant = await catalog.get_merchant(db)
    goals = list(await db.scalars(select(Goal).where(Goal.merchant_id == session.merchant_id)))
    shop = ShopFacts(
        merchant.shop_name,
        merchant.shop_description,
        merchant.negotiation_instructions,
        tuple(goal.instructions for goal in goals),
    )
    messages = [
        {"role": "system", "content": build_system_prompt(shop)},
        {"role": "system", "content": build_state_block(StateView(state="intro", language=language))},
    ]

    async def no_tool(name, arguments):
        return {"error": "TOOL_NOT_ALLOWED"}

    return await run_tool_loop(
        llm,
        messages,
        [],
        no_tool,
        lambda: set(),
        fallback=languages.require(language).sample,
        valid=lambda text: matches_language_script(text, language),
        on_fallback=on_fallback,
    )


async def customer_turn(
    db: AsyncSession, hubs: Hubs, llm: LLMClient, sid: uuid.UUID, text: str, pinned: str | None = None
) -> str:
    session = await sessions.get_session(db, sid)
    merchant = await catalog.get_merchant(db)
    language = resolve_turn_language(
        pinned=pinned,
        stt_language=None,
        text=text,
        session_language=session.language,
        shop_languages=merchant.languages,
    )
    if language != session.language:
        session.language = language
        await db.commit()
    if re.search(
        r"\b(?:ignore|forget|override|bypass)\b.{0,60}\b(?:rules?|instructions?|system|polic(?:y|ies))\b",
        text,
        re.IGNORECASE | re.DOTALL,
    ):
        return (
            languages.require(language).refuse_instruction
            if language
            else "Sorry, I cannot change the shop’s rules. We can continue shopping."
        )
    goals = list(await db.scalars(select(Goal).where(Goal.merchant_id == session.merchant_id)))
    basket = await views.public_basket(db, sid)
    history = await views.recent_transcripts(db, sid, 10)
    shop = ShopFacts(
        merchant.shop_name,
        merchant.shop_description,
        merchant.negotiation_instructions,
        tuple(goal.instructions for goal in goals),
    )
    # Briefing is merchant-only; customers see the pending review phase.
    customer_state = (
        SessionState.pending_merchant if session.state == SessionState.briefing else session.state
    )
    offer_rows = list(
        await db.scalars(select(Offer).where(Offer.session_id == sid).order_by(Offer.created_at, Offer.id))
    )
    all_products = list(await db.scalars(select(Product).where(Product.merchant_id == session.merchant_id)))
    names = {p.product_id: p.product_name for p in all_products}
    latest = {}
    for offer in offer_rows:
        for item in offer.items:
            pid = item["product_id"]
            latest[pid] = DecisionView(
                f"{names.get(pid, pid)} (product ID {pid})",
                offer.round,
                offer.decision,
                str(int(offer.price)) if offer.price is not None and len(offer.items) == 1 else None,
                offer.final,
            )
    active = await views.active_mandate(db, sid) if customer_state == SessionState.negotiating else None
    view = StateView(
        state=customer_state.value,
        language=language,
        intent=session.intent,
        decisions=tuple(latest.values()),
        mandate=active.readable if active else None,
        basket=tuple(
            BasketLineView(line.product_name, line.qty, str(int(line.line_total))) for line in basket.lines
        ),
    )
    searches = list(
        await db.scalars(
            select(ToolCallTrace)
            .where(
                ToolCallTrace.session_id == sid,
                ToolCallTrace.channel == "customer",
                ToolCallTrace.name == "search_products",
            )
            .order_by(ToolCallTrace.created_at.desc(), ToolCallTrace.id.desc())
            .limit(5)
        )
    )
    found = {}
    for search in reversed(searches):
        for product in search.result.get("products", []):
            found[product["product_id"]] = product
    public_catalog = json.dumps(list(found.values()), ensure_ascii=False)
    state_block = build_state_block(view)
    if found:
        state_body, language_instruction = state_block.rsplit("\n", 1)
        state_block = (
            state_body
            + "\nPublic products from prior searches (use the exact product IDs): "
            + public_catalog
            + "\n"
            + language_instruction
        )
    messages = [
        {"role": "system", "content": build_system_prompt(shop)},
        {"role": "system", "content": state_block},
        *[{"role": "user" if m.speaker == "customer" else "assistant", "content": m.text} for m in history],
    ]
    products = all_products
    customer_messages = list(
        await db.scalars(
            select(Message).where(
                Message.session_id == sid, Message.channel == "customer", Message.speaker == "customer"
            )
        )
    )
    approved: set[Decimal] = set()

    async def refresh() -> None:
        nonlocal approved, offer_rows
        offer_rows = list(await db.scalars(select(Offer).where(Offer.session_id == sid)))
        current_basket = await views.public_basket(db, sid)
        approved = allowed_amounts(
            GuardFacts(
                listed={p.product_id: p.listed_price for p in products},
                offers=[{"price": o.price, "line_prices": o.line_prices} for o in offer_rows],
                basket_total=current_basket.total,
                customer_amounts=[amount for m in customer_messages for amount in extract_amounts(m.text)],
            )
        )

    await refresh()

    def exposed_tools():
        phase = SessionState.pending_merchant if session.state == SessionState.briefing else session.state
        return tool_schemas(phase)

    above_listed = False

    async def execute(name, arguments):
        nonlocal above_listed
        permitted = {tool["function"]["name"] for tool in exposed_tools()}
        result = (
            await dispatch(ToolContext(db, hubs, sid), name, arguments)
            if name in permitted
            else {"error": "TOOL_NOT_ALLOWED"}
        )
        await trace.record_tool_call(db, hubs.merchant, sid, "customer", name, arguments, result)
        await refresh()
        above_listed |= result.get("error") == "OFFER_ABOVE_LISTED"
        return result

    reply = await run_tool_loop(
        llm,
        messages,
        exposed_tools,
        execute,
        lambda: approved,
        fallback=languages.require(language).retry if language else "Sorry, could you say that again?",
        valid=lambda reply: matches_language_script(reply, language),
    )
    if above_listed:
        reply = (
            languages.require(language).retry
            if language
            else "That offer is above the listed price. Could you clarify your offer?"
        )
    await db.refresh(session)
    if session.state == SessionState.intro:
        await sessions.transition(db, hubs, sid, SessionState.discovery)
    elif session.state == SessionState.discovery and len(customer_messages) >= 4:
        await sessions.transition(db, hubs, sid, SessionState.negotiating)
    return reply


async def resume_customer(db: AsyncSession, hubs: Hubs, llm: LLMClient, sid: uuid.UUID) -> None:
    """Pitch a confirmed multi-product mandate using an engine quote, never its private rules."""
    from app.agent.prompt import language_pin
    from app.schemas.events import TranscriptEvent
    from app.services import offers

    session = await sessions.get_session(db, sid)
    mandate = await views.active_mandate(db, sid)
    ids = list(dict.fromkeys(r["product_id"] for r in mandate.rules.get("rules", []))) if mandate else []
    quote = await offers.suggest_bundle(db, hubs, sid, ids) if len(ids) >= 2 else None
    if quote:
        await trace.record_tool_call(
            db, hubs.merchant, sid, "customer", "suggest_bundle", {"product_ids": ids}, quote
        )
        names = {p.product_id: p.product_name for p in await catalog.list_products(db)}
        price = Decimal(quote["bundle_price"])
        messages = [
            {
                "role": "system",
                "content": "You are Hermion. Offer this engine-quoted bundle to the customer in one short sentence. Do not mention the shopkeeper's private instructions. "
                + language_pin(session.language),
            },
            {
                "role": "user",
                "content": f"Bundle: {', '.join(names.get(pid, pid) for pid in ids)}. Engine price: ₹{price}.",
            },
        ]

        async def no_tool(name, arguments):
            return {"error": "TOOL_NOT_ALLOWED"}

        reply = await run_tool_loop(
            llm,
            messages,
            [],
            no_tool,
            lambda: {price},
            fallback=languages.require(session.language).retry
            if session.language
            else "Sorry, could you say that again?",
            valid=lambda text: matches_language_script(text, session.language),
        )
    else:

        async def no_tool(name, arguments):
            return {"error": "TOOL_NOT_ALLOWED"}

        reply = await run_tool_loop(
            llm,
            [
                {
                    "role": "system",
                    "content": "Tell the customer the shopkeeper is ready to continue and ask what they would like to offer. Do not state any price. "
                    + language_pin(session.language),
                },
                {"role": "user", "content": "Please continue the negotiation."},
            ],
            [],
            no_tool,
            lambda: set(),
            fallback=languages.require(session.language).retry
            if session.language
            else "Sorry, could you say that again?",
            valid=lambda text: matches_language_script(text, session.language),
        )
    await trace.record_message(db, hubs.merchant, sid, channel="customer", speaker="hermion", text=reply)
    await hubs.customer.send(sid, TranscriptEvent(speaker="hermion", text=reply))
