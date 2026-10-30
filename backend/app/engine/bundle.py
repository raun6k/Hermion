"""Bundle suggestion. Spec: docs/engine.md#concession-policy (suggest_bundle)."""

from decimal import Decimal

from app.engine.basket import split_basket_amount
from app.engine.concession import _validate, line_terms
from app.engine.money import ceil_to_10
from app.engine.types import Decision, Evaluation, NegotiationContext, OfferItem, ProductTerms, ReasonCode


def suggest_bundle(
    products: dict[str, ProductTerms], items: list[OfferItem], ctx: NegotiationContext
) -> Evaluation | None:
    """Price for taking all `items` together: ceil_to_10(sum T_i x qty_i) with the basket signal.

    Returned as an accepted-if-agreed evaluation. Does not advance rounds: each product is priced at
    its current round (at least 1).
    """
    if len(items) < 2 or not ctx.bundle_allowed or _validate(products, items) is not None:
        return None
    rounds = {i.product_id: max(ctx.rounds.get(i.product_id, 0), 1) for i in items}
    lines = line_terms(products, items, rounds, False, ctx)
    weights = {line.item.product_id: line.weight for line in lines}
    total_t = sum(weights.values(), Decimal(0))
    total_listed = sum((line.listed_total for line in lines), Decimal(0))
    price = min(ceil_to_10(total_t), total_listed)
    return Evaluation(
        Decision.accept,
        ReasonCode.ACCEPTABLE,
        round=max(rounds.values()),
        final=False,
        price=price,
        line_prices=tuple(split_basket_amount(price, weights, items)),
        threshold=total_t,
        signals=tuple(sorted(set().union(*(line.signals for line in lines)))),
        mandate_applied=any(line.mandate_applied for line in lines),
    )
