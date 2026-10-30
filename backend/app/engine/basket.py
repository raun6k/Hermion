"""Basket-scope split and re-check. Spec: docs/engine.md#concession-policy (Basket scope)."""

from decimal import Decimal

from app.engine.types import LinePrice, OfferItem, ProductTerms


def split_basket_amount(
    amount: Decimal, weights: dict[str, Decimal], items: list[OfferItem]
) -> list[LinePrice]:
    raise NotImplementedError


def recheck_lines(products: dict[str, ProductTerms], lines: list[LinePrice]) -> list[LinePrice]:
    """Return the lines still valid (stock, rules) before the merchant sees the basket."""
    raise NotImplementedError
