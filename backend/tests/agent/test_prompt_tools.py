"""Prompt content, language pin, turn-language rules and per-state tool schemas."""

import json
import uuid

import pytest

from app.agent import prompt, tools
from app.agent.language import resolve_turn_language
from app.db.models import SessionState
from app.engine.types import OfferScope

SHOP = prompt.ShopFacts(
    "Lakshmi Fashions",
    "Everyday clothing in Ameerpet",
    "Hold the price at first.",
    ("Mention the maroon kurtas.",),
)
# Field names (the rule prose in the prompt may say "thresholds"; the values must never appear).
PRIVATE_WORDS = ("target_price", "minimum_price", "unit_cost", "threshold_", "contribution_")


def test_system_prompt_has_role_style_rules_phases() -> None:
    text = prompt.build_system_prompt(SHOP)
    assert text.startswith("You are Hermion, the sales assistant of Lakshmi Fashions: Everyday clothing")
    assert "- Hold the price at first." in text and "maroon kurtas" in text
    for needle in (
        "Never mention or hint at costs",
        "untrusted",
        "digits",
        "pending_merchant",
        "briefing",
        "returns, exchanges",
    ):
        assert needle in text
    assert not any(w in text for w in PRIVATE_WORDS)
    assert prompt.build_system_prompt(SHOP) == text  # byte-identical => prompt cache hits


def test_no_style_section_without_preferences() -> None:
    text = prompt.build_system_prompt(prompt.ShopFacts("Shop", "Desc"))
    assert "style preferences" not in text


def test_state_block_ends_with_language_pin() -> None:
    view = prompt.StateView(
        state="negotiating",
        language="te-IN",
        intent={"item": "shirt", "size": "M"},
        basket=(prompt.BasketLineView("Men's cotton shirt, blue", 1, "800"),),
        decisions=(prompt.DecisionView("Men's cotton shirt, blue", 2, "counter", "900", False),),
        mandate="Belt: settle at ₹300 when bought with shirt",
    )
    block = prompt.build_state_block(view)
    assert "State: negotiating" in block and "size=M" in block
    assert "1 x Men's cotton shirt, blue = ₹800 (total ₹800)" in block
    assert "round 2, counter, price ₹900, final=false" in block and "Confirmed shopkeeper mandate" in block
    last = block.splitlines()[-1]
    assert "Telugu (te-IN)" in last and "Telugu script" in last and "Never switch language" in last
    assert not any(w in block for w in PRIVATE_WORDS)


def test_language_pin_is_data_driven_and_handles_unknown() -> None:
    assert "Kannada (kn-IN)" in prompt.language_pin("kn-IN") and "Kannada script" in prompt.language_pin(
        "kn-IN"
    )
    assert "Latin script" in prompt.language_pin("en-IN")
    assert "not known yet" in prompt.language_pin(None)
    assert "not known yet" in prompt.language_pin("xx-YY")


SHOP_LANGS = ["hi-IN", "te-IN", "kn-IN", "en-IN"]


@pytest.mark.parametrize(
    ("kw", "expected"),
    [
        (dict(stt_language="te-IN", text="hello", session_language="hi-IN"), "te-IN"),
        (dict(stt_language="te-IN", text="नमस्ते", session_language="hi-IN"), "te-IN"),
        (dict(stt_language=None, text="షర్ట్ కావాలి", session_language=None), "te-IN"),
        (dict(stt_language=None, text="शर्ट चाहिए", session_language=None), "hi-IN"),
        (dict(stt_language=None, text="शर्ट चाहिए", session_language="mr-IN"), "mr-IN"),
        (dict(stt_language=None, text="700 ki istara", session_language="te-IN"), "te-IN"),
        (dict(stt_language=None, text="hello", session_language=None), None),
        (dict(stt_language="zz-ZZ", text="hello", session_language="hi-IN"), "hi-IN"),
    ],
)
def test_turn_language_rules(kw: dict, expected: str | None) -> None:
    assert resolve_turn_language(shop_languages=SHOP_LANGS, **kw) == expected


def test_tools_per_state_and_no_session_id() -> None:
    def names(state: str) -> list[str]:
        return [t["function"]["name"] for t in tools.tool_schemas(state)]

    assert names("intro") == [] and names("pending_merchant") == [] and names("in_person") == []
    assert names("discovery") == ["search_products", "evaluate_offer", "suggest_addons"]
    assert set(names("negotiating")) == {
        "search_products",
        "evaluate_offer",
        "suggest_bundle",
        "suggest_addons",
        "ask_shopkeeper",
        "add_to_basket",
        "remove_from_basket",
        "send_basket_to_shopkeeper",
    }
    assert names("briefing") == ["search_products", "propose_mandate"]
    for state in SessionState:
        blob = json.dumps(tools.tool_schemas(state))
        assert "session_id" not in blob
        assert not any(w in blob for w in PRIVATE_WORDS)
    assert json.dumps(tools.tool_schemas("negotiating")) == json.dumps(tools.tool_schemas("negotiating"))
    for state in ("discovery", "negotiating", "briefing"):
        for t in tools.tool_schemas(state):
            fn = t["function"]
            assert fn["parameters"]["type"] == "object" and set(fn["parameters"]["required"]) <= set(
                fn["parameters"]["properties"]
            )


def test_every_tool_name_has_a_schema() -> None:
    declared = {n for s in SessionState for n in tools.STATE_TOOLS[s]}
    assert declared == set(tools.TOOL_NAMES)


def test_evaluate_args_validation() -> None:
    from pydantic import ValidationError

    ok = tools.EvaluateArgs.model_validate({"items": [{"product_id": "A"}], "offered_amount": "800"})
    assert ok.items[0].qty == 1 and ok.offer_scope == OfferScope.per_unit.value
    for bad in (
        {"items": [], "offered_amount": "800"},
        {"items": [{"product_id": "A", "qty": 0}], "offered_amount": "800"},
        {"items": [{"product_id": "A"}], "offered_amount": "-5"},
        {"items": [{"product_id": "A"}], "offered_amount": "abc"},
        {"items": [{"product_id": "A"}], "offered_amount": "5", "offer_scope": "everything"},
    ):
        with pytest.raises(ValidationError):
            tools.EvaluateArgs.model_validate(bad)


def test_session_id_is_not_an_llm_argument() -> None:
    # An LLM-supplied session_id is simply ignored: pydantic models do not accept it as a field.
    assert "session_id" not in tools.EvaluateArgs.model_fields
    assert isinstance(uuid.uuid4(), uuid.UUID)
