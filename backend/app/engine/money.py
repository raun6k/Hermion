"""Rounding helpers (whole rupees). Spec: docs/engine.md#concession-policy."""

from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal

_TEN = Decimal(10)


def ceil_to_rupee(amount: Decimal) -> Decimal:
    return amount.to_integral_value(rounding=ROUND_CEILING)


def ceil_to_10(amount: Decimal) -> Decimal:
    return (amount / _TEN).to_integral_value(rounding=ROUND_CEILING) * _TEN


def floor_to_rupee(amount: Decimal) -> Decimal:
    return amount.to_integral_value(rounding=ROUND_FLOOR)


def clamp(value: Decimal, low: Decimal, high: Decimal) -> Decimal:
    return max(low, min(value, high))


__all__ = ["ceil_to_10", "ceil_to_rupee", "clamp", "floor_to_rupee"]
