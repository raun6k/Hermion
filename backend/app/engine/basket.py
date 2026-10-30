"""Basket-scope split and re-check. Spec: docs/engine.md#concession-policy (Basket scope)."""

from decimal import Decimal

from app.engine.types import LinePrice, OfferItem, ProductTerms


def split_basket_amount(
    amount: Decimal, weights: dict[str, Decimal], items: list[OfferItem]
) -> list[LinePrice]:
    """Split a whole-rupee `amount` across lines proportionally to `weights` (T_i x qty_i).

    Shares are floored, so with amount >= sum(weights) every line stays >= its weight; the leftover
    rupees go to the heaviest (most expensive) line. Lines sum exactly to `amount`.
    """
    total_weight = sum((weights[i.product_id] for i in items), Decimal(0))
    if total_weight <= 0:
        raise ValueError("weights must be positive")
    shares = [(amount * weights[i.product_id]) // total_weight for i in items]
    remainder = amount - sum(shares, Decimal(0))
    heaviest = max(range(len(items)), key=lambda n: (weights[items[n].product_id], -n))
    shares[heaviest] += remainder
    return [LinePrice(i.product_id, i.qty, share) for i, share in zip(items, shares, strict=True)]


def recheck_lines(products: dict[str, ProductTerms], lines: list[LinePrice]) -> list[LinePrice]:
    """Return the lines still valid (known product, enough stock, not below minimum) before the
    merchant sees the basket. Lines absent from the result must be dropped."""
    valid: list[LinePrice] = []
    for line in lines:
        product = products.get(line.product_id)
        if product is None or line.qty < 1 or line.qty > product.available_stock:
            continue
        if line.line_total < product.minimum_price * line.qty:
            continue
        valid.append(line)
    return valid
