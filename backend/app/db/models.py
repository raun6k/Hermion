"""SQLAlchemy models. Source of truth for columns: docs/data.md#tables."""

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    ARRAY,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

Money = Numeric(12, 2)


class Base(DeclarativeBase):
    pass


class SessionState(enum.StrEnum):
    """docs/architecture.md#session-state-machine"""

    intro = "intro"
    discovery = "discovery"
    negotiating = "negotiating"
    pending_merchant = "pending_merchant"
    briefing = "briefing"
    in_person = "in_person"
    accepted = "accepted"
    declined = "declined"
    exited = "exited"


TERMINAL_STATES = frozenset({SessionState.accepted, SessionState.declined, SessionState.exited})


class GoalType(enum.StrEnum):
    clear_stock = "clear_stock"
    preserve_stock = "preserve_stock"
    bigger_baskets = "bigger_baskets"


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class Merchant(Base):
    __tablename__ = "merchants"

    merchant_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    shop_name: Mapped[str] = mapped_column(String(200))
    shop_description: Mapped[str] = mapped_column(Text, default="")
    languages: Mapped[list[str]] = mapped_column(ARRAY(String(16)))
    negotiation_instructions: Mapped[str] = mapped_column(Text, default="")
    # Legacy persisted flags are always-on at the service layer and are not exposed to merchants.
    bundle_allowed: Mapped[bool] = mapped_column(Boolean, default=True)
    qr_token: Mapped[str] = mapped_column(String(64), unique=True)
    escalation: Mapped[str] = mapped_column(String(16), default="serious")  # never|serious|rare|when_close
    escalation_gap_pct: Mapped[int] = mapped_column(Integer, default=5)
    upsell_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # Legacy setup proposal column retained for existing databases; the setup chat was removed.
    pending_style: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)


class Product(Base):
    __tablename__ = "products"

    product_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.merchant_id"), index=True)
    product_name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(64))
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    aliases: Mapped[list[str]] = mapped_column(ARRAY(String(100)), default=list)
    listed_price: Mapped[Decimal] = mapped_column(Money)
    target_price: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    minimum_price: Mapped[Decimal] = mapped_column(Money)
    unit_cost: Mapped[Decimal] = mapped_column(Money)
    available_stock: Mapped[int] = mapped_column(Integer)
    negotiable: Mapped[bool] = mapped_column(Boolean, default=True)
    # Negotiator-only facts the merchant provided (public). docs/data.md#tables
    pitch: Mapped[str | None] = mapped_column(Text, nullable=True)
    selling_points: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    specs: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    best_for: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    objection_replies: Mapped[list[dict[str, str]] | None] = mapped_column(JSONB, nullable=True)
    pairs_with_ids: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    upsell_ids: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)


class Goal(Base):
    __tablename__ = "goals"

    goal_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.merchant_id"), index=True)
    goal_type: Mapped[GoalType] = mapped_column(Enum(GoalType, name="goal_type"))
    product_ids: Mapped[list[str]] = mapped_column(ARRAY(String(64)), default=list)
    instructions: Mapped[str] = mapped_column(Text, default="")


class Session(Base):
    __tablename__ = "sessions"

    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.merchant_id"), index=True)
    device_id: Mapped[str] = mapped_column(String(64), index=True)
    state: Mapped[SessionState] = mapped_column(
        Enum(SessionState, name="session_state"), default=SessionState.intro
    )
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    intent: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    # Customer consent for basket adds: {stage, evaluation_id, turn, asked} (docs/engine.md#basket-consent)
    consent: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    escalations: Mapped[int] = mapped_column(Integer, default=0)
    # Open "ask the shopkeeper" request: {evaluation_id, items, offered_amount} (docs/engine.md#escalation)
    pending_check: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    customer_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source: Mapped[str] = mapped_column(String(8), default="live")  # live | seed (synthetic history)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.session_id"), index=True)
    channel: Mapped[str] = mapped_column(String(16))  # customer | briefing
    speaker: Mapped[str] = mapped_column(String(16))  # customer | hermion | merchant
    text: Mapped[str] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    text_translated: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TurnTiming(Base):
    __tablename__ = "turn_timings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.session_id"), index=True)
    message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("messages.id"))
    measurements: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StateChange(Base):
    __tablename__ = "state_changes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.session_id"), index=True)
    from_state: Mapped[str] = mapped_column(String(24))
    to_state: Mapped[str] = mapped_column(String(24))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ToolCallTrace(Base):
    __tablename__ = "tool_calls"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.session_id"), index=True)
    channel: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(64))
    arguments: Mapped[dict[str, Any]] = mapped_column(JSONB)
    result: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Offer(Base):
    """Engine log; id is the evaluation_id."""

    __tablename__ = "offers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.session_id"), index=True)
    items: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    offered_amount: Mapped[Decimal] = mapped_column(Money)
    offer_scope: Mapped[str] = mapped_column(String(16))
    signals: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    decision: Mapped[str] = mapped_column(String(16))
    price: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    line_prices: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    reason_code: Mapped[str] = mapped_column(String(32))
    round: Mapped[int] = mapped_column(Integer)
    final: Mapped[bool] = mapped_column(Boolean, default=False)
    threshold: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    profile: Mapped[str | None] = mapped_column(String(16), nullable=True)  # merchant-only
    headroom: Mapped[str | None] = mapped_column(String(8), nullable=True)  # merchant-only
    mandate_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("mandates.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BasketLine(Base):
    __tablename__ = "basket_lines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.session_id"), index=True)
    offer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("offers.id"), nullable=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.product_id"))
    qty: Mapped[int] = mapped_column(Integer)
    line_total: Mapped[Decimal] = mapped_column(Money)
    below_minimum: Mapped[bool] = mapped_column(Boolean, default=False)
    edited_by_merchant: Mapped[bool] = mapped_column(Boolean, default=False)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Mandate(Base):
    __tablename__ = "mandates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.session_id"), index=True)
    rules: Mapped[dict[str, Any]] = mapped_column(JSONB)
    readable: Mapped[str] = mapped_column(Text)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    replaced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
