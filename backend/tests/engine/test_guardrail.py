"""Range, guard and strategy bars (docs/engine.md#range-and-guard). Hypothesis properties + worked cases."""

from decimal import Decimal as D

from hypothesis import given, settings
from hypothesis import strategies as st

from app.engine.concession import evaluate_offer
from app.engine.guardrail import LEAK_STEP, Headroom, guard_proposal, headroom
from app.engine.types import (
    Decision,
    LinePrice,
    NegotiationContext,
    OfferItem,
    OfferScope,
    ProductTerms,
    ReasonCode,
)

SHIRT = ProductTerms("SHIRT", D(1000), D(800), D(750), 15, True)
CATALOG = {"SHIRT": SHIRT}
ITEMS = [OfferItem("SHIRT", 1)]


def ev(amount, *, proposed=None, rounds=0, buy_now=False, last=()):
    ctx = NegotiationContext(rounds={"SHIRT": rounds}, last_counter=tuple(last))
    return evaluate_offer(
        CATALOG,
        ITEMS,
        D(amount),
        OfferScope.per_unit,
        buy_now,
        ctx,
        None if proposed is None else D(proposed),
    )


def test_headroom_buckets_never_expose_numbers() -> None:
    assert headroom(D(1000), D(750), D(1000)) is Headroom.high
    assert headroom(D(850), D(750), D(1000)) is Headroom.medium
    assert headroom(D(770), D(750), D(1000)) is Headroom.low
    assert headroom(D(750), D(750), D(1000)) is Headroom.none


def test_first_offer_below_target_is_countered_not_accepted() -> None:
    # T(2) = 900 here; even a lower threshold never accepts a first offer below target.
    r = ev(780, rounds=0, buy_now=True)
    assert r.decision is Decision.counter and r.price >= 780


def test_first_offer_at_or_above_threshold_and_target_is_accepted() -> None:
    r = ev(950, rounds=0)
    assert r.decision is Decision.accept and r.reason_code is ReasonCode.ACCEPTABLE


def test_closing_below_target_carries_its_reason() -> None:
    r = ev(775, rounds=4, buy_now=True)  # e = 5: T = 775, after the rounds are used
    assert r.decision is Decision.accept and r.reason_code is ReasonCode.CLOSING_BELOW_TARGET


def test_proposal_in_range_is_approved_as_proposed() -> None:
    r = ev(700, proposed=900, rounds=1)
    assert (r.decision, r.price, r.reason_code) == (Decision.counter, 900, ReasonCode.COUNTER)
    assert r.headroom == "high"


def test_proposal_below_floor_gets_a_safe_counter_that_is_not_the_floor() -> None:
    r = ev(600, proposed=400, rounds=1)
    assert r.reason_code is ReasonCode.PROPOSAL_BELOW_FLOOR
    assert r.price == 750 + LEAK_STEP != 750


def test_proposal_above_listed_is_clamped() -> None:
    assert ev(700, proposed=5000, rounds=1).price == 1000


def test_proposal_below_customer_offer_is_raised_to_it() -> None:
    assert ev(900, proposed=800, rounds=1).price >= 900


def test_customer_taking_our_counter_is_accepted_even_below_the_schedule() -> None:
    held = [LinePrice("SHIRT", 1, D(780))]
    r = ev(780, rounds=1, last=held)
    assert r.decision is Decision.accept and r.price == 780


def test_hermion_can_hold_out_for_more_on_an_acceptable_offer() -> None:
    assert ev(900, rounds=1).decision is Decision.accept  # acceptable, no proposal: closes
    r = ev(900, proposed=960, rounds=1)
    assert (r.decision, r.price, r.reason_code) == (Decision.counter, 960, ReasonCode.HELD_FOR_MORE)
    assert r.acceptable and not r.final
    # A proposal at or below the offer is just a yes.
    assert ev(900, proposed=900, rounds=1).decision is Decision.accept
    # On the last counter round there is no more holding out.
    assert ev(850, proposed=950, rounds=3).decision is Decision.accept


def test_holding_out_never_overrides_a_customer_taking_our_counter() -> None:
    held = [LinePrice("SHIRT", 1, D(900))]
    r = ev(900, proposed=980, rounds=1, last=held)
    assert r.decision is Decision.accept and r.price == 900


def test_held_counter_below_floor_is_ignored() -> None:
    held = [LinePrice("SHIRT", 1, D(700))]
    assert ev(700, rounds=1, last=held).decision is not Decision.accept


@settings(max_examples=300, deadline=None)
@given(
    offered=st.integers(1, 1000),
    proposed=st.integers(1, 1500),
    rounds=st.integers(0, 3),
    buy_now=st.booleans(),
)
def test_proposals_never_leave_the_range(offered, proposed, rounds, buy_now) -> None:
    r = ev(offered, proposed=proposed, rounds=rounds, buy_now=buy_now)
    if r.price is None:
        return
    assert 750 <= r.price <= 1000
    assert r.price >= offered
    if r.decision is Decision.counter:
        assert r.price != 750  # the counter never reveals the floor
    if r.decision is Decision.accept:
        assert r.price == offered
    assert sum(lp.line_total for lp in r.line_prices) == r.price
    assert all(lp.line_total >= 750 for lp in r.line_prices)


@given(proposed=st.integers(1, 1500), offered=st.integers(1, 749))
def test_probing_below_floor_never_reads_the_floor(proposed, offered) -> None:
    r = ev(offered, proposed=proposed, rounds=1)
    assert r.price is not None and r.price != 750


def test_guard_proposal_unit() -> None:
    assert guard_proposal(D(400), D(300), D(750), D(1000)) == (D(760), True)
    assert guard_proposal(D(900), D(300), D(750), D(1000)) == (D(900), False)


def test_escalation_only_for_a_close_high_intent_offer_below_floor() -> None:
    from app.engine.escalation import should_escalate

    f = D(750)
    assert should_escalate("rare", D(720), f, 5, True, 0)  # 4% under, high intent
    assert not should_escalate("rare", D(720), f, 5, False, 0)  # no intent
    assert should_escalate("when_close", D(720), f, 5, False, 0)
    assert not should_escalate("rare", D(600), f, 5, True, 0)  # too far
    assert should_escalate("rare", D(720), f, 5, True, 1)  # one used, cap is two
    assert not should_escalate("rare", D(720), f, 5, True, 2)  # cap used
    assert not should_escalate("never", D(720), f, 5, True, 0)
    assert not should_escalate("rare", D(760), f, 5, True, 0)  # at or above floor


def test_serious_mode_asks_for_any_below_floor_offer_from_a_serious_buyer() -> None:
    from app.engine.escalation import should_escalate

    f = D(750)
    assert should_escalate("serious", D(600), f, 5, False, 0)  # far below, no intent: still asks
    assert not should_escalate("serious", D(600), f, 5, False, 0, serious=False)  # lowballer
    assert not should_escalate("serious", D(760), f, 5, True, 0)  # inside the range: Hermion's job
    assert not should_escalate("serious", D(600), f, 5, True, 2)  # cap used


def test_behavior_profiles() -> None:
    from app.engine.behavior import BehaviorFeatures, Profile, classify

    base = dict(
        offers=1,
        opening_ratio=D("0.8"),
        last_step_ratio=None,
        repeats=0,
        hesitation=0,
        qty_or_bundle=False,
        buy_now=False,
        walk_away=False,
    )
    assert classify(BehaviorFeatures(**base)) is Profile.value_seeker
    assert classify(BehaviorFeatures(**{**base, "opening_ratio": D("0.4")})) is Profile.lowballer
    assert classify(BehaviorFeatures(**{**base, "buy_now": True})) is Profile.ready_to_buy
    assert classify(BehaviorFeatures(**{**base, "walk_away": True})) is Profile.browsing
    assert classify(BehaviorFeatures(**{**base, "repeats": 2})) is Profile.browsing
