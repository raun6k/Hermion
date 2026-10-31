"""Healthy price range and proposal guard. Spec: docs/engine.md#range-and-guard.

Hermion proposes a counter; this module decides what is allowed. Pure: totals in, totals out.
`floor` and `target` never leave the engine; callers only see the coarse `Headroom` bucket.
"""

from decimal import Decimal
from enum import StrEnum

from app.engine.money import ceil_to_rupee

# A counter is never the floor itself, so repeated probing cannot read the floor off the counters.
LEAK_STEP = Decimal(10)


class Headroom(StrEnum):
    high = "high"
    medium = "medium"
    low = "low"
    none = "none"


def headroom(price: Decimal, floor_total: Decimal, listed_total: Decimal) -> Headroom:
    """How much room Hermion still has below `price`, as a share of the floor..listed range."""
    span = listed_total - floor_total
    if span <= 0 or price <= floor_total:
        return Headroom.none
    share = (price - floor_total) / span
    if share >= Decimal("0.5"):
        return Headroom.high
    if share >= Decimal("0.25"):
        return Headroom.medium
    return Headroom.low


def safe_floor(floor_total: Decimal, listed_total: Decimal) -> Decimal:
    """Lowest counter ever shown: one step above the floor (never the floor), capped at listed."""
    return min(listed_total, ceil_to_rupee(floor_total) + LEAK_STEP)


def guard_proposal(
    proposed: Decimal, offered: Decimal, floor_total: Decimal, listed_total: Decimal
) -> tuple[Decimal, bool]:
    """Clamp a proposed counter into [max(offered, safe_floor), listed].

    Returns (price, below_floor): `below_floor` is True when the proposal was under the safe floor and
    was replaced by a safe alternative.
    """
    lower = max(offered, safe_floor(floor_total, listed_total))
    price = max(lower, min(proposed, listed_total))
    return price, proposed < safe_floor(floor_total, listed_total)
