"""Mandate rule application. Spec: docs/engine.md#mandates."""

from decimal import Decimal

from app.engine.money import ceil_to_rupee, clamp
from app.engine.types import MandateRule, OfferItem, ProductTerms


def mandate_threshold(
    product: ProductTerms,
    rules: tuple[MandateRule, ...],
    items: list[OfferItem],
    basket: frozenset[str],
) -> Decimal | None:
    """Per-unit threshold forced by a confirmed rule whose conditions hold, else None.

    A rule holds when every condition is met: `min_qty` on the evaluated line, and
    `with_product_id` in the same evaluation or already in the basket. `settle_at` is clamped to
    [minimum, listed]. If several rules hold, the highest wins (the merchant never loses by overlap).
    """
    qty = next((i.qty for i in items if i.product_id == product.product_id), 1)
    others = ({i.product_id for i in items} | basket) - {product.product_id}
    best: Decimal | None = None
    for rule in rules:
        if rule.product_id != product.product_id:
            continue
        if rule.min_qty is not None and qty < rule.min_qty:
            continue
        if rule.with_product_id is not None and rule.with_product_id not in others:
            continue
        value = ceil_to_rupee(clamp(rule.settle_at, product.minimum_price, product.listed_price))
        best = value if best is None else max(best, value)
    return best
