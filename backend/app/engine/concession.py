"""Threshold and offer decision. Spec: docs/engine.md#concession-policy."""

from decimal import Decimal

from app.engine.types import Evaluation, NegotiationContext, OfferItem, OfferScope, ProductTerms


def threshold(product: ProductTerms, effective_round: int) -> Decimal:
    raise NotImplementedError


def evaluate_offer(
    products: dict[str, ProductTerms],
    items: list[OfferItem],
    offered_amount: Decimal,
    scope: OfferScope,
    buy_now: bool,
    ctx: NegotiationContext,
) -> Evaluation:
    raise NotImplementedError
