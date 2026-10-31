"""Playwright-only app with a deterministic scripted model; never used by the normal server."""

import json
import re

from app.agent.llm_client import FakeLLMClient, LLMResponse, ToolCall


class DemoLLM(FakeLLMClient):
    async def complete(self, messages, tools=None):
        tool_names = {item["function"]["name"] for item in tools or []}
        last_user = next((str(m.get("content", "")) for m in reversed(messages) if m["role"] == "user"), "")
        if messages[-1]["role"] == "tool":
            result = json.loads(messages[-1]["content"])
            preceding = messages[-2]["tool_calls"][0]["function"]["name"]
            if (
                preceding == "suggest_bundle"
                or (preceding == "evaluate_offer" and result.get("decision") == "accept")
            ) and "add_to_basket" in tool_names:
                return LLMResponse(
                    None, [ToolCall("add", "add_to_basket", {"evaluation_id": result["evaluation_id"]})]
                )
            if preceding == "evaluate_offer" and result.get("price"):
                return LLMResponse(f"The price is ₹{result['price']}.")
            if preceding == "propose_mandate":
                return LLMResponse("Please confirm the proposed terms.")
            if preceding == "add_to_basket":
                return LLMResponse("The item is in your basket.")
            return LLMResponse("I found the blue shirt. What would you like to offer?")
        if "propose_mandate" in tool_names:
            return LLMResponse(
                None,
                [
                    ToolCall(
                        "mandate",
                        "propose_mandate",
                        {
                            "rules": [
                                {
                                    "product_id": "SHIRT-BLU-M",
                                    "settle_at": "850",
                                    "with_product_id": "BELT-BRN-32",
                                },
                                {
                                    "product_id": "BELT-BRN-32",
                                    "settle_at": "300",
                                    "with_product_id": "SHIRT-BLU-M",
                                },
                            ]
                        },
                    )
                ],
            )
        if "suggest_bundle" in tool_names and "accept bundle" in last_user.lower():
            return LLMResponse(
                None, [ToolCall("bundle", "suggest_bundle", {"product_ids": ["SHIRT-BLU-M", "BELT-BRN-32"]})]
            )
        if "evaluate_offer" in tool_names:
            amount = re.search(r"\b(\d{3,4})\b", last_user)
            if amount:
                return LLMResponse(
                    None,
                    [
                        ToolCall(
                            "evaluate",
                            "evaluate_offer",
                            {
                                "items": [
                                    {
                                        "product_id": "BELT-BRN-32"
                                        if "belt" in last_user.lower()
                                        else "SHIRT-BLU-M",
                                        "qty": 1,
                                    }
                                ],
                                "offered_amount": amount.group(1),
                                "buy_now": "now" in last_user.lower(),
                            },
                        )
                    ],
                )
            if "search_products" in tool_names and "shirt" in last_user.lower():
                return LLMResponse(None, [ToolCall("search", "search_products", {"query": "blue shirt M"})])
        return LLMResponse(f"Namaste! I am Hermion (fake LLM). You said: {last_user}")


import app.main  # noqa: E402

app.main.build_llm_client = lambda settings: DemoLLM()
app = app.main.create_app()
