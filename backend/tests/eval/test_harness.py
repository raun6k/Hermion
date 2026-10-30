"""The eval harness runs end to end on fakes, and its bars actually bite."""

import uuid
from decimal import Decimal as D

from app.db.models import Offer
from app.engine.types import OfferItem, OfferScope
from app.services import offers
from tests.eval.run_scenarios import (
    EvalContext,
    SkeletonRunner,
    reply_in_language,
    run_scenario,
    summarize,
)
from tests.eval.scenarios import Scenario, load_scenarios
from tests.helpers import run_db


def test_scenario_file_covers_the_required_cases() -> None:
    scenarios = load_scenarios()
    ids = {s.scenario_id.split("-", 1)[1] for s in scenarios}
    assert len(scenarios) == 12
    assert {
        "happy-path",
        "lowballer",
        "prompt-injection",
        "quantity-deal",
        "basket-scope",
        "fixed-price",
        "out-of-stock-size",
        "code-mixed-hinglish",
        "telugu-native-script",
        "kannada-non-demo-language",
        "exit-midway",
        "briefing-mandate",
    } == ids
    assert {s.language for s in scenarios} >= {"te-IN", "hi-IN", "kn-IN", "en-IN"}


def test_harness_runs_all_scenarios_on_fakes(reseed) -> None:
    async def go(db):
        runner = SkeletonRunner()
        return [await run_scenario(db, sc, runner) for sc in load_scenarios()]

    results = run_db(go)
    summary = summarize(results)
    assert summary["run"] == 11 and summary["skipped"] == ["S12-briefing-mandate"]
    assert not any(summary["hard"].values()), summary
    exit_run = next(r for r in results if r.scenario_id == "S11-exit-midway")
    assert exit_run.final_state == "exited" and len(exit_run.replies) == 2
    assert summary["report"]["turn_latency_ms_p50"] is not None


class _Cheater(SkeletonRunner):
    """Misbehaves on purpose: sells below the minimum, says private numbers, replies in the wrong language."""

    async def turn(self, ctx: EvalContext, text: str) -> str:
        from sqlalchemy import update

        r = await offers.evaluate(
            ctx.db, ctx.hubs, ctx.session_id, [OfferItem("SHIRT-BLU-M", 1)], D(2000), OfferScope.line, False
        )
        # corrupt the log row to look like an under-minimum sale
        await ctx.db.execute(
            update(Offer).where(Offer.id == uuid.UUID(r["evaluation_id"])).values(price=D(500))
        )
        await ctx.db.commit()
        return "Sure, ₹750 is my minimum and my cost is 630. Okay."


def test_harness_flags_violations(reseed) -> None:
    async def go(db):
        sc = Scenario.model_validate(
            {
                "scenario_id": "X-bad",
                "merchant_id": "M001",
                "language": "te-IN",
                "messages": ["shirt"],
                "expect_deal": False,
            }
        )
        return await run_scenario(db, sc, _Cheater())

    r = run_db(go)
    assert r.below_minimum == 1
    assert r.guard_violations >= 1 and r.private_leaks >= 1  # 750 (minimum) and 630 (cost)
    assert r.wrong_language == 1
    assert r.injection_price_changes == 1 and r.hard_failures >= 5


def test_reply_language_check() -> None:
    assert reply_in_language("నమస్కారం, నేను హెర్మియన్. ₹850", "te-IN")
    assert not reply_in_language("Hello, I am Hermion", "te-IN")
    assert reply_in_language("Hello, I am Hermion. ₹850", "en-IN")
    assert not reply_in_language("नमस्ते", "en-IN")
    assert reply_in_language("₹850", "kn-IN")  # no letters => nothing to contradict
