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
