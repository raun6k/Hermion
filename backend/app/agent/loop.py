"""Customer tool loop and legacy greeting runner used by the Stage 1 evaluation harness."""

import logging

from app.agent.llm_client import LLMClient, LLMError

log = logging.getLogger(__name__)

SKELETON_SYSTEM_PROMPT = (
    "You are Hermion, a friendly shop assistant. This is a connectivity test: "
    "reply with one short greeting sentence in the customer's language."
)
FALLBACK_REPLY = "Sorry, one moment, could you say that again?"


async def run_turn(llm: LLMClient, customer_text: str) -> str:
    messages = [
        {"role": "system", "content": SKELETON_SYSTEM_PROMPT},
        {"role": "user", "content": customer_text},
    ]
    try:
        resp = await llm.complete(messages)
    except LLMError:
        log.exception("llm call failed")
        return FALLBACK_REPLY
    return (resp.text or "").strip() or FALLBACK_REPLY


async def run_tool_loop(
    llm, messages, tools, dispatch, allowed, fallback=FALLBACK_REPLY, valid=lambda _: True, on_fallback=None
):
    """Run at most three sequential tools and guard the final customer reply.

    The caller supplies the dispatcher and refreshes the allowed amounts after each tool.
    """
    import json

    from app.agent.guard import check_reply

    messages = list(messages)

    def use_fallback():
        if on_fallback:
            on_fallback()
        return fallback

    latest_price = None
    for step in range(4):
        try:
            response = await llm.complete(messages, tools=tools() if callable(tools) else tools)
        except LLMError:
            log.exception("llm call failed")
            return use_fallback()
        if response.tool_calls:
            if step == 3:
                return use_fallback()
            call = response.tool_calls[0]
            messages.append(
                {
                    "role": "assistant",
                    "content": response.text,
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.name,
                                "arguments": json.dumps(call.arguments, ensure_ascii=False),
                            },
                        }
                    ],
                }
            )
            result = await dispatch(call.name, call.arguments)
            if call.name in {"evaluate_offer", "suggest_bundle"}:
                latest_price = result.get("price") or result.get("bundle_price")
            messages.append(
                {"role": "tool", "tool_call_id": call.id, "content": json.dumps(result, ensure_ascii=False)}
            )
            continue
        reply = (response.text or "").strip()
        if not reply:
            return use_fallback()
        if not check_reply(reply, allowed()) and valid(reply):
            return reply
        messages.append({"role": "assistant", "content": reply})
        messages.append(
            {
                "role": "user",
                "content": "Please restate that in the pinned language and do not use unverified prices.",
            }
        )
        try:
            retry = await llm.complete(messages, tools=tools() if callable(tools) else tools)
        except LLMError:
            log.exception("llm regeneration failed")
            return use_fallback()
        reply = (retry.text or "").strip()
        if reply and not retry.tool_calls and not check_reply(reply, allowed()) and valid(reply):
            return reply
        if latest_price is not None:
            template = f"The price is ₹{latest_price}."
            if not check_reply(template, allowed()) and valid(template):
                return template
        return use_fallback()
    return use_fallback()
