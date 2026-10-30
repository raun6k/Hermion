"""Rounding helpers (whole rupees). Spec: docs/engine.md#concession-policy."""

from decimal import Decimal


def ceil_to_rupee(amount: Decimal) -> Decimal:
    raise NotImplementedError


def ceil_to_10(amount: Decimal) -> Decimal:
    raise NotImplementedError


def floor_to_rupee(amount: Decimal) -> Decimal:
    raise NotImplementedError
