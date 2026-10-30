"""Merchant mandates: propose from validated rules, confirm, resume negotiation (docs/engine.md#mandates)."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Mandate, Product, SessionState
from app.engine.money import ceil_to_rupee, clamp
from app.schemas.common import AppError
from app.schemas.merchant import MandateProposal
from app.services import sessions, trace, views
from app.services.hub import Hubs

S = SessionState
MAX_RULES = 6


class RuleArgs(BaseModel):
    """One `propose_mandate` rule as the LLM states it: a price for a product under optional conditions."""

    product_id: str
    settle_at: Decimal = Field(ge=0)
    min_qty: int | None = Field(default=None, ge=1)
    with_product_id: str | None = None


class MandateArgs(BaseModel):
    rules: list[RuleArgs] = Field(min_length=1, max_length=MAX_RULES)


def describe(rule: RuleArgs, names: dict[str, str]) -> str:
    name = names[rule.product_id]
    parts = []
    if rule.min_qty:
        parts.append(f"{rule.min_qty} or more are bought")
    if rule.with_product_id:
        parts.append(f"it is bought with {names[rule.with_product_id]}")
    when = f" when {' and '.join(parts)}" if parts else ""
    return f"{name}: settle at ₹{int(rule.settle_at)}{when}"


async def propose(
    db: AsyncSession, hubs: Hubs | None, session_id: uuid.UUID, args: MandateArgs
) -> tuple[Mandate, MandateProposal]:
    """Store an unconfirmed mandate. `readable` echoes the merchant's own figures (safe for the LLM);
    stored `settle_at` is clamped to [minimum, listed] and `limited` marks rules that needed it."""
    session = await sessions.get_session(db, session_id)
    sessions.require_state(session, S.briefing)
    ids = {r.product_id for r in args.rules} | {r.with_product_id for r in args.rules if r.with_product_id}
    products = {p.product_id: p for p in await db.scalars(select(Product).where(Product.product_id.in_(ids)))}
    if missing := sorted(ids - products.keys()):
        raise AppError("UNKNOWN_PRODUCT", f"Unknown product(s): {', '.join(missing)}", 404)
    rules: list[dict[str, Any]] = []
    for r in args.rules:
        p = products[r.product_id]
        applied = ceil_to_rupee(clamp(r.settle_at, p.minimum_price, p.listed_price))
        rules.append(
            {
                "product_id": r.product_id,
                "settle_at": str(applied),
                "min_qty": r.min_qty,
                "with_product_id": r.with_product_id,
                "limited": applied != r.settle_at,
            }
        )
    names = {pid: p.product_name for pid, p in products.items()}
    readable = "\n".join(describe(r, names) for r in args.rules)
    mandate = Mandate(session_id=session_id, rules={"rules": rules}, readable=readable)
    # A newer proposal supersedes unconfirmed ones; the confirmed mandate is replaced on confirm.
    for old in await db.scalars(
        select(Mandate).where(
            Mandate.session_id == session_id, Mandate.confirmed_at.is_(None), Mandate.replaced_at.is_(None)
        )
    ):
        old.replaced_at = datetime.now(UTC)
    db.add(mandate)
    await db.commit()
    await db.refresh(mandate)
    proposal = views.mandate_proposal(mandate)
    if hubs is not None:
        await trace.push_mandate(hubs.merchant, session_id, "proposed", proposal)
    return mandate, proposal


async def confirm(db: AsyncSession, hubs: Hubs, session_id: uuid.UUID, mandate_id: uuid.UUID) -> SessionState:
    session = await sessions.get_session(db, session_id)
    sessions.require_state(session, S.briefing)
    mandate = await db.get(Mandate, mandate_id)
    if mandate is None or mandate.session_id != session_id or mandate.replaced_at is not None:
        raise AppError("MANDATE_NOT_FOUND", "Unknown or superseded mandate", 404)
    now = datetime.now(UTC)
    for old in await db.scalars(
        select(Mandate).where(
            Mandate.session_id == session_id, Mandate.confirmed_at.is_not(None), Mandate.replaced_at.is_(None)
        )
    ):
        old.replaced_at = now
    mandate.confirmed_at = now
    await db.commit()
    await trace.push_mandate(hubs.merchant, session_id, "confirmed", views.mandate_proposal(mandate))
    session = await sessions.transition(db, hubs, session_id, S.negotiating)
    return session.state
