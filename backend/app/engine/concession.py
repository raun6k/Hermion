"""Threshold and offer decision. Spec: docs/engine.md#concession-policy."""

from dataclasses import dataclass
from decimal import Decimal

from app.engine.basket import split_basket_amount
from app.engine.mandate import mandate_threshold
from app.engine.money import ceil_to_10, ceil_to_rupee, clamp, floor_to_rupee
from app.engine.types import (
    MAX_ROUNDS,
    Decision,
    Evaluation,
    NegotiationContext,
    OfferItem,
    OfferScope,
    ProductTerms,
    ReasonCode,
)


def effective_target(product: ProductTerms) -> Decimal:
    """Merchant's target, defaulting to the midpoint of listed and minimum; always in [minimum, listed]."""
    target = product.target_price
    if target is None:
        target = (product.listed_price + product.minimum_price) / 2
    return clamp(target, product.minimum_price, product.listed_price)


def threshold(product: ProductTerms, effective_round: int) -> Decimal:
    """Per-unit price at or above which an offer is acceptable in this effective round."""
    listed, minimum, target = product.listed_price, product.minimum_price, effective_target(product)
    e = max(effective_round, 0)
    if e <= MAX_ROUNDS:
        t = listed - (listed - target) * e / MAX_ROUNDS
    else:
        t = target - (target - minimum) * (e - MAX_ROUNDS) / 2
    return ceil_to_rupee(max(t, minimum))


@dataclass(frozen=True)
class LineTerms:
    item: OfferItem
    product: ProductTerms
    round: int
    signals: frozenset[str]
    threshold: Decimal  # per unit, after overrides
    mandate_applied: bool

    @property
    def weight(self) -> Decimal:
        return self.threshold * self.item.qty

    @property
    def listed_total(self) -> Decimal:
        return self.product.listed_price * self.item.qty


def line_terms(
    products: dict[str, ProductTerms],
    items: list[OfferItem],
    rounds: dict[str, int],
    buy_now: bool,
    ctx: NegotiationContext,
) -> list[LineTerms]:
    """Per-line thresholds. `rounds[pid]` is the round this evaluation counts as for that product."""
    present = {i.product_id for i in items} | ctx.basket_product_ids
    out: list[LineTerms] = []
    for item in items:
        product = products[item.product_id]
        signals: set[str] = set()
        if buy_now:
            signals.add("buy_now")
        if item.qty >= 2:
            signals.add("qty")
        if present - {item.product_id}:
            signals.add("basket")
        if item.product_id in ctx.clear_stock:
            signals.add("clear_stock")
        rnd = rounds[item.product_id]
        t = threshold(product, min(rnd, MAX_ROUNDS) + len(signals))
        if item.product_id in ctx.preserve_stock:
            t = max(t, ceil_to_rupee(effective_target(product)))
        forced = mandate_threshold(product, ctx.mandate_rules, items, ctx.basket_product_ids)
        if forced is not None:
            t = forced
        if not product.negotiable:
            t = product.listed_price
        out.append(LineTerms(item, product, rnd, frozenset(signals), t, forced is not None))
    return out


def _reject(code: ReasonCode, **kw) -> Evaluation:
    return Evaluation(decision=Decision.reject, reason_code=code, round=kw.pop("round", 0), final=False, **kw)


def _validate(products: dict[str, ProductTerms], items: list[OfferItem]) -> ReasonCode | None:
    ids = [i.product_id for i in items]
    if not items or len(set(ids)) != len(ids) or any(i.qty < 1 for i in items):
        return ReasonCode.INVALID_OFFER
    for item in items:
        if item.product_id not in products:
            return ReasonCode.UNKNOWN_PRODUCT
    for item in items:
        stock = products[item.product_id].available_stock
        if stock <= 0:
            return ReasonCode.OUT_OF_STOCK
        if item.qty > stock:
            return ReasonCode.INSUFFICIENT_STOCK
    return None


def evaluate_offer(
    products: dict[str, ProductTerms],
    items: list[OfferItem],
    offered_amount: Decimal,
    scope: OfferScope,
    buy_now: bool,
    ctx: NegotiationContext,
) -> Evaluation:
    """Decide on a customer offer. `offered_amount` is per unit, for the line, or for the basket
    depending on `scope`; it is rounded down to whole rupees."""
    if scope in (OfferScope.per_unit, OfferScope.line) and len(items) != 1:
        return _reject(ReasonCode.INVALID_OFFER)
    if len(items) > 1 and not ctx.bundle_allowed:
        return _reject(ReasonCode.BUNDLE_NOT_ALLOWED)
    if (code := _validate(products, items)) is not None:
        return _reject(code)
    offered = floor_to_rupee(offered_amount)
    if offered < 1:
        return _reject(ReasonCode.INVALID_OFFER)
    if scope is OfferScope.per_unit:
        offered *= items[0].qty

    rounds = {i.product_id: ctx.rounds.get(i.product_id, 0) + 1 for i in items}
    lines = line_terms(products, items, rounds, buy_now, ctx)
    rnd = max(rounds.values())
    signals = tuple(sorted(set().union(*(line.signals for line in lines))))
    mandate = any(line.mandate_applied for line in lines)
    weights = {line.item.product_id: line.weight for line in lines}
    total_t = sum(weights.values(), Decimal(0))
    total_listed = sum((line.listed_total for line in lines), Decimal(0))
    common = {"round": rnd, "threshold": total_t, "signals": signals, "mandate_applied": mandate}

    if offered >= total_t:
        price = min(offered, total_listed)
        return Evaluation(
            Decision.accept,
            ReasonCode.ACCEPTABLE,
            final=False,
            price=price,
            line_prices=tuple(split_basket_amount(price, weights, items)),
            **common,
        )
    if all(not line.product.negotiable for line in lines):
        listed_weights = {line.item.product_id: line.listed_total for line in lines}
        return Evaluation(
            Decision.reject,
            ReasonCode.FIXED_PRICE,
            final=True,
            price=total_listed,
            line_prices=tuple(split_basket_amount(total_listed, listed_weights, items)),
            **common,
        )
    counter = min(ceil_to_10(total_t), total_listed)
    prices = tuple(split_basket_amount(counter, weights, items))
    if rnd <= MAX_ROUNDS:
        final = rnd == MAX_ROUNDS
        return Evaluation(
            Decision.counter,
            ReasonCode.FINAL_OFFER if final else ReasonCode.COUNTER,
            final=final,
            price=counter,
            line_prices=prices,
            **common,
        )
    return Evaluation(
        Decision.reject, ReasonCode.ROUNDS_EXHAUSTED, final=True, price=counter, line_prices=prices, **common
    )
