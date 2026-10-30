"""Agent turn loop. Walking skeleton: one plain LLM call, no tools, no state machine.

Real loop (docs/engine.md#agent-loop): system prompt + state block + last 10 messages,
<= 3 tool calls one at a time, output guard, failure templates.
"""

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
