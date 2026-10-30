"""Output guard: every amount Hermion says must be engine-approved. Spec: docs/engine.md#output-guard."""

from decimal import Decimal


def extract_amounts(text: str) -> list[Decimal]:
    raise NotImplementedError


def check_reply(text: str, allowed: set[Decimal]) -> list[Decimal]:
    """Return the amounts in `text` that are not allowed (empty list = pass)."""
    raise NotImplementedError
