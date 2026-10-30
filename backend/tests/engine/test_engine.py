"""Engine bars (docs/build-plan.md#test-and-eval-bars): worked examples + Hypothesis properties."""

from decimal import Decimal as D

from hypothesis import given, settings
from hypothesis import strategies as st

from app.engine.basket import recheck_lines, split_basket_amount
from app.engine.bundle import suggest_bundle
from app.engine.concession import evaluate_offer, threshold
from app.engine.mandate import mandate_threshold
from app.engine.money import ceil_to_10, ceil_to_rupee, floor_to_rupee
from app.engine.types import (
    MAX_ROUNDS,
    Decision,
    LinePrice,
    MandateRule,
    NegotiationContext,
    OfferItem,
    OfferScope,
    ProductTerms,
    ReasonCode,
)

SHIRT = ProductTerms("SHIRT", D(1000), D(800), D(750), 15, True)
BELT = ProductTerms("BELT", D(500), D(400), D(300), 12, True)
SOCKS = ProductTerms("SOCKS", D(250), None, D(250), 30, False)
OOS = ProductTerms("OOS", D(950), D(780), D(720), 0, True)
LOW = ProductTerms("LOW", D(1000), D(800), D(750), 2, True)
CATALOG = {p.product_id: p for p in (SHIRT, BELT, SOCKS, OOS, LOW)}


def ctx(**kw) -> NegotiationContext:
    kw.setdefault("rounds", {})
    return NegotiationContext(**kw)


def ev(pid, amount, *, qty=1, scope=OfferScope.per_unit, buy_now=False, c=None, catalog=CATALOG):
    return evaluate_offer(catalog, [OfferItem(pid, qty)], D(amount), scope, buy_now, c or ctx())


# ---- rounding ---------------------------------------------------------------------


def test_rounding() -> None:
    assert ceil_to_rupee(D("874.2")) == 875
    assert ceil_to_10(D("875")) == 880
    assert ceil_to_10(D("880")) == 880
    assert floor_to_rupee(D("799.99")) == 799


# ---- worked examples --------------------------------------------------------------


def test_thresholds_for_demo_shirt() -> None:
    assert [threshold(SHIRT, e) for e in range(1, 8)] == [950, 900, 850, 800, 775, 750, 750]


def test_missing_target_defaults_to_midpoint() -> None:
    p = ProductTerms("P", D(1000), None, D(800), 5, True)
    assert threshold(p, 4) == 900


def test_worked_example_700_750_800_buy_now() -> None:
    first = ev("SHIRT", 700)
    assert (first.decision, first.price, first.round, first.reason_code) == (
        Decision.counter,
        950,
        1,
        ReasonCode.COUNTER,
    )
    second = ev("SHIRT", 750, c=ctx(rounds={"SHIRT": 1}))
    assert (second.decision, second.price) == (Decision.counter, 900)
    third = ev("SHIRT", 800, buy_now=True, c=ctx(rounds={"SHIRT": 2}))
    assert (third.decision, third.price, third.signals) == (Decision.accept, 800, ("buy_now",))


def test_qty_two_buy_now_round_four_gives_minimum() -> None:
    r = ev("SHIRT", 1500, qty=2, scope=OfferScope.line, buy_now=True, c=ctx(rounds={"SHIRT": 3}))
    assert r.decision is Decision.accept and r.price == 1500
    below = ev("SHIRT", 1499, qty=2, scope=OfferScope.line, buy_now=True, c=ctx(rounds={"SHIRT": 3}))
    assert below.threshold == 1500  # T = 750 per unit


def test_final_offer_then_rounds_exhausted() -> None:
    final = ev("SHIRT", 100, c=ctx(rounds={"SHIRT": 3}))
    assert (final.decision, final.reason_code, final.final, final.price) == (
        Decision.counter,
        ReasonCode.FINAL_OFFER,
        True,
        800,
    )
    out = ev("SHIRT", 100, c=ctx(rounds={"SHIRT": 4}))
    assert (out.decision, out.reason_code, out.price) == (Decision.reject, ReasonCode.ROUNDS_EXHAUSTED, 800)
    # an offer at the threshold is still accepted after the rounds are used up
    assert ev("SHIRT", 800, c=ctx(rounds={"SHIRT": 9})).decision is Decision.accept


def test_accept_never_below_customer_offer_or_above_listed() -> None:
    assert ev("SHIRT", 900, c=ctx(rounds={"SHIRT": 2})).price == 900
    assert ev("SHIRT", 5000).price == 1000


def test_offer_rounded_down_to_rupee() -> None:
    assert ev("SHIRT", "949.99").decision is Decision.counter
    assert ev("SHIRT", "950.99").decision is Decision.accept


def test_fixed_price() -> None:
    r = ev("SOCKS", 150)
    assert (r.decision, r.reason_code, r.price, r.final) == (
        Decision.reject,
        ReasonCode.FIXED_PRICE,
        250,
        True,
    )
    ok = ev("SOCKS", 250)
    assert (ok.decision, ok.price) == (Decision.accept, 250)


def test_error_codes() -> None:
    assert ev("NOPE", 100).reason_code is ReasonCode.UNKNOWN_PRODUCT
    assert ev("OOS", 800).reason_code is ReasonCode.OUT_OF_STOCK
    assert ev("LOW", 2400, qty=3, scope=OfferScope.line).reason_code is ReasonCode.INSUFFICIENT_STOCK
    assert ev("SHIRT", 0).reason_code is ReasonCode.INVALID_OFFER
    assert ev("SHIRT", 100, qty=0, scope=OfferScope.line).reason_code is ReasonCode.INVALID_OFFER
    for r in (ev("NOPE", 100), ev("OOS", 800)):
        assert r.decision is Decision.reject and r.round == 0 and r.price is None


def test_basket_scope_requires_bundle_allowed() -> None:
    items = [OfferItem("SHIRT", 1), OfferItem("BELT", 1)]
    r = evaluate_offer(CATALOG, items, D(1100), OfferScope.basket, False, ctx(bundle_allowed=False))
    assert r.reason_code is ReasonCode.BUNDLE_NOT_ALLOWED


def test_basket_split_example() -> None:
    items = [OfferItem("SHIRT", 1), OfferItem("BELT", 1)]
    # basket signal: shirt e=2 -> 900, belt e=2 -> 450; total 1350
    r = evaluate_offer(CATALOG, items, D(1100), OfferScope.basket, False, ctx(bundle_allowed=True))
    assert (r.decision, r.price, r.threshold) == (Decision.counter, 1350, 1350)
    ok = evaluate_offer(CATALOG, items, D(1400), OfferScope.basket, False, ctx(bundle_allowed=True))
    assert ok.decision is Decision.accept and ok.price == 1400
    assert sum(lp.line_total for lp in ok.line_prices) == 1400
    assert all(lp.line_total >= D(t) for lp, t in zip(ok.line_prices, (900, 450), strict=True))


def test_basket_signal_from_existing_basket() -> None:
    alone = ev("BELT", 100)
    with_basket = ev("BELT", 100, c=ctx(basket_product_ids=frozenset({"SHIRT"})))
    assert alone.price == 480 and with_basket.price == 450
    assert "basket" in with_basket.signals


def test_clear_stock_and_preserve_stock() -> None:
    assert ev("SHIRT", 100, c=ctx(clear_stock=frozenset({"SHIRT"}))).price == 900
    kept = ev("SHIRT", 100, c=ctx(rounds={"SHIRT": 3}, preserve_stock=frozenset({"SHIRT"})))
    assert kept.price == 800
    assert ev("SHIRT", 100, c=ctx(rounds={"SHIRT": 6}, preserve_stock=frozenset({"SHIRT"}))).price == 800


# ---- mandates ---------------------------------------------------------------------

PAIR = (
    MandateRule("SHIRT", D(850), with_product_id="BELT"),
    MandateRule("BELT", D(300), with_product_id="SHIRT"),
)


def test_mandate_applies_only_when_condition_holds() -> None:
    items = [OfferItem("SHIRT", 1)]
    assert mandate_threshold(SHIRT, PAIR, items, frozenset()) is None
    assert mandate_threshold(SHIRT, PAIR, items, frozenset({"BELT"})) == 850
    both = [OfferItem("SHIRT", 1), OfferItem("BELT", 1)]
    assert mandate_threshold(BELT, PAIR, both, frozenset()) == 300


def test_mandate_clamps_to_limits_so_a_free_belt_is_refused() -> None:
    rules = (MandateRule("BELT", D(0), with_product_id="SHIRT"), MandateRule("SHIRT", D(5000)))
    assert mandate_threshold(BELT, rules, [OfferItem("BELT", 1)], frozenset({"SHIRT"})) == 300
    assert mandate_threshold(SHIRT, rules, [OfferItem("SHIRT", 1)], frozenset()) == 1000


def test_mandate_min_qty_and_overlap() -> None:
    rules = (MandateRule("SHIRT", D(900), min_qty=3), MandateRule("SHIRT", D(850), min_qty=2))
    assert mandate_threshold(SHIRT, rules, [OfferItem("SHIRT", 1)], frozenset()) is None
    assert mandate_threshold(SHIRT, rules, [OfferItem("SHIRT", 2)], frozenset()) == 850
    assert mandate_threshold(SHIRT, rules, [OfferItem("SHIRT", 3)], frozenset()) == 900


def test_bundle_with_mandate_prices_the_pair() -> None:
    c = ctx(bundle_allowed=True, mandate_rules=PAIR, rounds={"SHIRT": 3, "BELT": 0})
    b = suggest_bundle(CATALOG, [OfferItem("SHIRT", 1), OfferItem("BELT", 1)], c)
    assert b is not None and b.decision is Decision.accept and b.mandate_applied
    assert b.price == 1150
    assert {lp.product_id: lp.line_total for lp in b.line_prices} == {"SHIRT": 850, "BELT": 300}


def test_suggest_bundle_guards() -> None:
    items = [OfferItem("SHIRT", 1), OfferItem("BELT", 1)]
    assert suggest_bundle(CATALOG, items, ctx(bundle_allowed=False)) is None
    assert suggest_bundle(CATALOG, [OfferItem("SHIRT", 1)], ctx(bundle_allowed=True)) is None
    assert (
        suggest_bundle(CATALOG, [OfferItem("SHIRT", 1), OfferItem("OOS", 1)], ctx(bundle_allowed=True))
        is None
    )


def test_mandate_stays_within_limits_in_evaluation() -> None:
    c = ctx(
        mandate_rules=(MandateRule("BELT", D(0), with_product_id="SHIRT"),),
        basket_product_ids=frozenset({"SHIRT"}),
    )
    r = ev("BELT", 1, c=c)
    assert r.decision is Decision.counter and r.price == 300 and r.mandate_applied


# ---- split / recheck --------------------------------------------------------------


def test_split_remainder_goes_to_most_expensive_line() -> None:
    items = [OfferItem("A", 1), OfferItem("B", 1), OfferItem("C", 1)]
    out = split_basket_amount(D(100), {"A": D(10), "B": D(10), "C": D(20)}, items)
    assert [lp.line_total for lp in out] == [D(25), D(25), D(50)]
    out = split_basket_amount(D(101), {"A": D(10), "B": D(10), "C": D(20)}, items)
    assert sum(lp.line_total for lp in out) == 101 and out[2].line_total == 51


def test_recheck_drops_invalid_lines() -> None:
    lines = [
        LinePrice("SHIRT", 1, D(800)),
        LinePrice("SHIRT", 1, D(700)),  # below minimum
        LinePrice("LOW", 3, D(2400)),  # stock 2
        LinePrice("OOS", 1, D(800)),
        LinePrice("GONE", 1, D(800)),
    ]
    assert recheck_lines(CATALOG, lines) == [lines[0]]


# ---- properties -------------------------------------------------------------------


@st.composite
def products(draw, pid="P"):
    minimum = draw(st.integers(1, 5000))
    target = minimum + draw(st.integers(0, 3000))
    listed = target + draw(st.integers(0, 3000))
    return ProductTerms(
        pid,
        D(listed),
        D(target) if draw(st.booleans()) else None,
        D(minimum),
        draw(st.integers(1, 20)),
        draw(st.booleans()),
    )


@st.composite
def scenarios(draw):
    n = draw(st.integers(1, 3))
    prods = {f"P{i}": draw(products(f"P{i}")) for i in range(n)}
    items = [OfferItem(pid, draw(st.integers(1, min(p.available_stock, 4)))) for pid, p in prods.items()]
    scope = OfferScope.basket if n > 1 else draw(st.sampled_from([OfferScope.line, OfferScope.per_unit]))
    ids = list(prods)
    rules = tuple(
        MandateRule(
            draw(st.sampled_from(ids)),
            D(draw(st.integers(0, 12000))),
            min_qty=draw(st.one_of(st.none(), st.integers(1, 3))),
            with_product_id=draw(st.one_of(st.none(), st.sampled_from(ids))),
        )
        for _ in range(draw(st.integers(0, 3)))
    )
    c = NegotiationContext(
        rounds={pid: draw(st.integers(0, 8)) for pid in ids},
        basket_product_ids=frozenset(draw(st.sets(st.sampled_from(ids + ["X"])))),
        clear_stock=frozenset(draw(st.sets(st.sampled_from(ids)))),
        preserve_stock=frozenset(draw(st.sets(st.sampled_from(ids)))),
        mandate_rules=rules,
        bundle_allowed=True,
    )
    return prods, items, scope, D(draw(st.integers(1, 40000))), draw(st.booleans()), c


def _min_total(prods, items):
    return sum((prods[i.product_id].minimum_price * i.qty for i in items), D(0))


def _listed_total(prods, items):
    return sum((prods[i.product_id].listed_price * i.qty for i in items), D(0))


@settings(max_examples=400, deadline=None)
@given(scenarios())
def test_price_bounds_hold_for_any_input(s) -> None:
    prods, items, scope, offer, buy_now, c = s
    r = evaluate_offer(prods, items, offer, scope, buy_now, c)
    if r.price is None:
        return
    assert r.price >= _min_total(prods, items)  # never below minimum
    assert r.price <= _listed_total(prods, items)  # never above listed
    if r.decision is not Decision.reject or r.reason_code is ReasonCode.ROUNDS_EXHAUSTED:
        assert r.price >= min(
            floor_to_rupee(offer) * (items[0].qty if scope is OfferScope.per_unit else 1),
            _listed_total(prods, items),
        )
    assert r.price == sum(lp.line_total for lp in r.line_prices)


@settings(max_examples=400, deadline=None)
@given(scenarios())
def test_each_line_covers_its_threshold_and_minimum(s) -> None:
    prods, items, scope, offer, buy_now, c = s
    r = evaluate_offer(prods, items, offer, scope, buy_now, c)
    if r.decision is Decision.accept or r.decision is Decision.counter:
        for lp in r.line_prices:
            assert lp.line_total >= prods[lp.product_id].minimum_price * lp.qty
        assert r.threshold is not None and r.price >= min(r.threshold, _listed_total(prods, items))


@settings(max_examples=300, deadline=None)
@given(scenarios(), st.integers(1, 400), st.integers(1, 400))
def test_same_round_and_signals_give_same_counter_below_threshold(s, a, b) -> None:
    prods, items, scope, _, buy_now, c = s
    first = evaluate_offer(prods, items, D(a), scope, buy_now, c)
    second = evaluate_offer(prods, items, D(b), scope, buy_now, c)
    if first.decision is not Decision.accept and second.decision is not Decision.accept:
        assert (first.price, first.reason_code, first.round) == (
            second.price,
            second.reason_code,
            second.round,
        )


@settings(max_examples=300, deadline=None)
@given(scenarios())
def test_bundle_never_below_minimum(s) -> None:
    prods, items, _, _, _, c = s
    b = suggest_bundle(prods, items, c)
    if b is None:
        return
    assert _min_total(prods, items) <= b.price <= _listed_total(prods, items)
    assert b.price == sum(lp.line_total for lp in b.line_prices)


@given(
    st.integers(0, 100000),
    st.lists(st.integers(1, 5000), min_size=1, max_size=5),
    st.integers(0, 3000),
)
def test_split_sums_and_covers_weights(extra, weights, add) -> None:
    items = [OfferItem(f"P{i}", 1) for i in range(len(weights))]
    w = {f"P{i}": D(x) for i, x in enumerate(weights)}
    amount = sum(w.values(), D(0)) + add
    out = split_basket_amount(amount, w, items)
    assert sum(lp.line_total for lp in out) == amount
    assert all(lp.line_total >= w[lp.product_id] for lp in out)


def test_threshold_monotonic_and_bounded() -> None:
    values = [threshold(SHIRT, e) for e in range(0, MAX_ROUNDS * 3)]
    assert values == sorted(values, reverse=True)
    assert values[0] == SHIRT.listed_price and values[-1] == SHIRT.minimum_price
