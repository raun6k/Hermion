"""Threshold and offer decision. Spec: docs/engine.md#concession-policy."""

from dataclasses import dataclass
from decimal import Decimal

from app.engine.basket import split_basket_amount
from app.engine.escalation import should_escalate
from app.engine.guardrail import Headroom, guard_proposal, headroom
from app.engine.mandate import mandate_threshold
from app.engine.money import ceil_to_10, ceil_to_rupee, clamp, floor_to_rupee
from app.engine.types import (
    MAX_ROUNDS,
    Decision,
    Evaluation,
    LinePrice,
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

    @property
    def floor(self) -> Decimal:
        """Lowest per-unit price this line may ever close at (>= minimum; stricter under goals/mandate)."""
        if not self.product.negotiable:
            return self.product.listed_price
        return max(self.product.minimum_price, self.floor_override)

    floor_override: Decimal = Decimal(0)


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
        floor = product.minimum_price
        if item.product_id in ctx.preserve_stock:
            t = max(t, ceil_to_rupee(effective_target(product)))
            floor = max(floor, ceil_to_rupee(effective_target(product)))
        forced = mandate_threshold(product, ctx.mandate_rules, items, ctx.basket_product_ids)
        if forced is not None:
            t = forced
            floor = max(floor, forced)
        if not product.negotiable:
            t = product.listed_price
        out.append(LineTerms(item, product, rnd, frozenset(signals), t, forced is not None, floor))
    return out


def _held_counter(
    ctx: NegotiationContext, items: list[OfferItem], lines: list["LineTerms"], total_floor: Decimal
) -> Decimal | None:
    """Total of Hermion's last counter for exactly these products and quantities, if it still clears the
    floor: a customer who takes our own counter always gets it."""
    previous = ctx.last_counter
    expected = {(i.product_id, i.qty) for i in items}
    if not previous or {(p.product_id, p.qty) for p in previous} != expected:
        return None
    total = sum((p.line_total for p in previous), Decimal(0))
    return total if total >= total_floor else None


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
    proposed: Decimal | None = None,
) -> Evaluation:
    """Decide on a customer offer. `offered_amount` is per unit, for the line, or for the basket
    depending on `scope`; it is rounded down to whole rupees.

    `proposed` is Hermion's counter for the whole evaluation (total rupees). When the engine would
    counter, the proposal replaces the schedule's counter after `guard_proposal` clamps it into the
    healthy range. Without it the schedule's counter is used.

    Hermion negotiates inside the range; the schedule only limits how fast it may concede. An offer at
    or above the schedule is acceptable, not automatically accepted: while counters remain, a proposal
    above the offer holds out for more (`HELD_FOR_MORE`, counter at the clamped proposal). Taking
    Hermion's own previous counter is always accepted.
    """
    if scope in (OfferScope.per_unit, OfferScope.line) and len(items) != 1:
        return _reject(ReasonCode.INVALID_OFFER)
    if len(items) > 1 and not ctx.bundle_allowed:
        return _reject(ReasonCode.BUNDLE_NOT_ALLOWED)
    if (code := _validate(products, items)) is not None:
        return _reject(code)
    listed_total = sum((products[i.product_id].listed_price * i.qty for i in items), Decimal(0))
    raw_total = offered_amount * items[0].qty if scope is OfferScope.per_unit else offered_amount
    if raw_total > listed_total:
        return _reject(ReasonCode.OFFER_ABOVE_LISTED)
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
    floor_weights = {line.item.product_id: line.floor * line.item.qty for line in lines}
    total_t = sum(weights.values(), Decimal(0))
    total_floor = sum(floor_weights.values(), Decimal(0))
    total_target = sum(
        (
            max(line.floor, ceil_to_rupee(effective_target(line.product))) * line.item.qty
            if not line.mandate_applied
            else line.threshold * line.item.qty
            for line in lines
        ),
        Decimal(0),
    )
    total_listed = sum((line.listed_total for line in lines), Decimal(0))
    escalate = should_escalate(
        ctx.escalation_mode,
        offered,
        total_floor,
        ctx.escalation_gap_pct,
        buy_now or len(items) > 1 or any(i.qty >= 2 for i in items),
        ctx.escalations_used,
        ctx.customer_serious,
    )
    common = {
        "round": rnd,
        "threshold": total_t,
        "signals": signals,
        "mandate_applied": mandate,
        "escalation_eligible": escalate,
    }

    def split(price: Decimal) -> tuple[LinePrice, ...]:
        # Every line must stay at or above its own floor, which can sit below its schedule threshold.
        return tuple(split_basket_amount(price, weights if price >= total_t else floor_weights, items))

    def shown(price: Decimal) -> str:
        return headroom(price, total_floor, total_listed).value

    held = _held_counter(ctx, items, lines, total_floor)
    first_offer = all(ctx.rounds.get(i.product_id, 0) == 0 for i in items)
    # An offer inside the acceptable range is an opening position, not a yes: the first one below the
    # target gets a counter (unless the merchant's mandate sets the price).
    premature = first_offer and offered < total_target and not mandate and total_target > total_floor
    takes_our_counter = held is not None and offered >= held
    acceptable = offered >= total_t and not premature
    if (
        acceptable
        and not takes_our_counter
        and proposed is not None
        and floor_to_rupee(proposed) > offered
        and rnd < MAX_ROUNDS
        and any(line.product.negotiable for line in lines)
    ):
        counter, _ = guard_proposal(floor_to_rupee(proposed), offered, total_floor, total_listed)
        return Evaluation(
            Decision.counter,
            ReasonCode.HELD_FOR_MORE,
            final=False,
            price=counter,
            line_prices=split(counter),
            headroom=shown(counter),
            acceptable=True,
            **common,
        )
    if acceptable or takes_our_counter:
        price = offered
        return Evaluation(
            Decision.accept,
            ReasonCode.ACCEPTABLE if offered >= total_target else ReasonCode.CLOSING_BELOW_TARGET,
            final=False,
            price=price,
            line_prices=split(price),
            headroom=shown(price),
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
            headroom=Headroom.none.value,
            **common,
        )
    counter = min(ceil_to_10(total_t), total_listed)
    code = None
    if proposed is not None and rnd <= MAX_ROUNDS:
        counter, below = guard_proposal(floor_to_rupee(proposed), offered, total_floor, total_listed)
        code = ReasonCode.PROPOSAL_BELOW_FLOOR if below else None
    elif premature:
        counter = max(counter, offered)
    if rnd <= MAX_ROUNDS:
        final = rnd == MAX_ROUNDS
        return Evaluation(
            Decision.counter,
            code or (ReasonCode.FINAL_OFFER if final else ReasonCode.COUNTER),
            final=final,
            price=counter,
            line_prices=split(counter),
            headroom=shown(counter),
            **common,
        )
    previous = ctx.last_counter
    current_terms = {line.item.product_id: line for line in lines}
    expected = {(item.product_id, item.qty) for item in items}
    valid = len(previous) == len(items) and {(p.product_id, p.qty) for p in previous} == expected
    if valid:
        valid = all(
            products[p.product_id].minimum_price * p.qty
            <= p.line_total
            <= products[p.product_id].listed_price * p.qty
            and (
                products[p.product_id].negotiable
                or p.line_total == products[p.product_id].listed_price * p.qty
            )
            and (
                p.product_id not in ctx.preserve_stock
                or p.line_total >= ceil_to_rupee(effective_target(products[p.product_id])) * p.qty
            )
            and (
                not current_terms[p.product_id].mandate_applied
                or p.line_total >= current_terms[p.product_id].threshold * p.qty
            )
            for p in previous
        )
    prior_total = sum((p.line_total for p in previous), Decimal(0))
    if not valid or prior_total < offered:
        return Evaluation(Decision.reject, ReasonCode.ROUNDS_EXHAUSTED, final=True, **common)
    return Evaluation(
        Decision.reject,
        ReasonCode.ROUNDS_EXHAUSTED,
        final=True,
        price=prior_total,
        line_prices=previous,
        **common,
    )
