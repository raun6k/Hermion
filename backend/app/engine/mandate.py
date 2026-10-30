"""Mandate rule application. Spec: docs/engine.md#mandates."""

from decimal import Decimal

from app.engine.types import MandateRule, OfferItem, ProductTerms


def mandate_threshold(
    product: ProductTerms, rules: tuple[MandateRule, ...], items: list[OfferItem], basket: frozenset[str]
) -> Decimal | None:
    raise NotImplementedError
