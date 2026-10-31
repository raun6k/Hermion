from app.agent.llm_client import FakeLLMClient, LLMError, LLMResponse
from app.agent.loop import FALLBACK_REPLY, run_turn


async def test_reply_comes_from_llm() -> None:
    llm = FakeLLMClient([LLMResponse(text="  Namaskaram!  ")])
    assert await run_turn(llm, "hi") == "Namaskaram!"
    assert llm.calls[0][-1] == {"role": "user", "content": "hi"}


async def test_llm_failure_uses_template() -> None:
    class Broken:
        async def complete(self, messages, tools=None):
            raise LLMError("timeout")

    assert await run_turn(Broken(), "hi") == FALLBACK_REPLY


async def test_empty_reply_uses_template() -> None:
    assert await run_turn(FakeLLMClient([LLMResponse(text=None)]), "hi") == FALLBACK_REPLY


async def test_tool_calls_are_sequential_and_bounded() -> None:
    from app.agent.llm_client import ToolCall
    from app.agent.loop import run_tool_loop

    llm = FakeLLMClient(
        [
            LLMResponse(
                text=None, tool_calls=[ToolCall("1", "search", {}), ToolCall("ignored", "search", {})]
            ),
            LLMResponse(text=None, tool_calls=[ToolCall("2", "search", {})]),
            LLMResponse(text=None, tool_calls=[ToolCall("3", "search", {})]),
            LLMResponse(text="Found it."),
        ]
    )
    calls = []

    async def dispatch(name, args):
        calls.append(name)
        return {"ok": True}

    reply = await run_tool_loop(llm, [{"role": "user", "content": "shirt"}], [], dispatch, lambda: set())
    assert reply == "Found it."
    assert calls == ["search"] * 3
    assert llm.calls[-1][-1]["role"] == "tool"


async def test_guard_regenerates_then_fails_closed() -> None:
    from app.agent.loop import run_tool_loop

    llm = FakeLLMClient([LLMResponse(text="₹750"), LLMResponse(text="₹700")])

    async def dispatch(name, args):
        raise AssertionError("unexpected tool")

    reply = await run_tool_loop(llm, [{"role": "user", "content": "hello"}], [], dispatch, lambda: set())
    assert reply == FALLBACK_REPLY
    assert len(llm.calls) == 2


async def test_language_validation_retries_and_uses_localized_fallback() -> None:
    from app.agent.language import matches_language_script
    from app.agent.loop import run_tool_loop

    llm = FakeLLMClient([LLMResponse(text="Hello"), LLMResponse(text="Sorry")])

    async def dispatch(name, args):
        raise AssertionError("unexpected tool")

    reply = await run_tool_loop(
        llm,
        [{"role": "user", "content": "नमस्ते"}],
        [],
        dispatch,
        lambda: set(),
        fallback="माफ़ कीजिए, फिर कहें।",
        valid=lambda text: matches_language_script(text, "hi-IN"),
    )
    assert reply == "माफ़ कीजिए, फिर कहें।"
    assert len(llm.calls) == 2
