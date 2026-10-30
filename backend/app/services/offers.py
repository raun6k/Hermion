"""Loads engine inputs from the DB, calls the pure engine, writes the `offers` log. Built in Stage 1."""

import uuid
from decimal import Decimal
from typing import Any


async def evaluate(
    session_id: uuid.UUID,
    items: list[dict[str, Any]],
    offered_amount: Decimal,
    offer_scope: str,
    buy_now: bool,
) -> dict[str, Any]:
    raise NotImplementedError
