"""Merchant-facing schemas (may contain private fields). Never use on customer routes."""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import Field

from app.schemas.common import LanguageList, Money, Schema, SessionStateName


class MerchantProfile(Schema):
    merchant_id: str
    shop_name: str
    shop_description: str
    languages: LanguageList
    negotiation_instructions: str
    bundle_allowed: bool
    qr_token: str


class MerchantPatch(Schema):
    shop_name: str | None = None
    shop_description: str | None = None
    languages: LanguageList | None = None
    negotiation_instructions: str | None = None
    bundle_allowed: bool | None = None


class ProductBase(Schema):
    product_name: str
    category: str
    attributes: dict[str, Any] = Field(default_factory=dict)
    aliases: list[str] = Field(default_factory=list)
    listed_price: Money
    target_price: Money | None = None
    minimum_price: Money
    unit_cost: Money
    available_stock: int
    negotiable: bool = True


class Product(ProductBase):
    product_id: str
    merchant_id: str


class ProductCreate(ProductBase):
    product_id: str


class ProductPatch(Schema):
    product_name: str | None = None
    category: str | None = None
    attributes: dict[str, Any] | None = None
    aliases: list[str] | None = None
    listed_price: Money | None = None
    target_price: Money | None = None
    minimum_price: Money | None = None
    unit_cost: Money | None = None
    available_stock: int | None = None
    negotiable: bool | None = None


class GoalTypeName(StrEnum):
    clear_stock = "clear_stock"
    preserve_stock = "preserve_stock"
    bigger_baskets = "bigger_baskets"


class Goal(Schema):
    goal_id: str
    goal_type: GoalTypeName
    product_ids: list[str] = Field(default_factory=list)
    instructions: str = ""


class SessionSummary(Schema):
    session_id: UUID
    state: SessionStateName
    language: str | None
    started_at: datetime
    ended_at: datetime | None
    line_count: int = 0
    basket_total: Money | None = None


class TraceMessage(Schema):
    id: UUID
    channel: str
    speaker: str
    text: str
    language: str | None
    text_translated: str | None
    created_at: datetime


class TraceOffer(Schema):
    id: UUID
    items: list[dict[str, Any]]
    offered_amount: Money
    offer_scope: str
    signals: dict[str, Any]
    decision: str
    price: Money | None
    line_prices: list[dict[str, Any]]
    reason_code: str
    round: int
    final: bool
    threshold: Money | None
    created_at: datetime


class MerchantBasketLine(Schema):
    product_id: str
    product_name: str
    qty: int
    listed_price: Money
    line_total: Money
    contribution: Money
    below_minimum: bool = False


class MerchantBasket(Schema):
    lines: list[MerchantBasketLine]
    total: Money
    contribution: Money


class MandateRule(Schema):
    product_id: str
    settle_at: Money
    when: dict[str, Any] = Field(default_factory=dict)


class MandateProposal(Schema):
    mandate_id: UUID
    readable: str
    rules: list[MandateRule]  # settle_at is the applied value, already clamped to [minimum, listed]
    limited_product_ids: list[str] = Field(default_factory=list)  # asked outside the catalog limits
    confirmed: bool = False


class TraceToolCall(Schema):
    id: UUID
    channel: str
    name: str
    arguments: dict[str, Any]
    result: dict[str, Any]
    created_at: datetime


class TraceStateChange(Schema):
    id: UUID
    from_state: str
    to_state: str
    created_at: datetime


class SessionTrace(Schema):
    session: SessionSummary
    messages: list[TraceMessage]
    offers: list[TraceOffer]
    tool_calls: list[TraceToolCall]
    state_changes: list[TraceStateChange]
    basket: MerchantBasket | None
    mandate: MandateProposal | None


class ReviewAction(StrEnum):
    accept = "accept"
    decline = "decline"
    renegotiate_hermion = "renegotiate_hermion"
    renegotiate_in_person = "renegotiate_in_person"


class ReviewRequest(Schema):
    action: ReviewAction


class ReviewResponse(Schema):
    state: SessionStateName


class MandateConfirmResponse(Schema):
    state: SessionStateName


class BriefingRequest(Schema):
    text: str


class BriefingResponse(Schema):
    reply: str
    proposed_mandate: MandateProposal | None = None


class BasketEditLine(Schema):
    product_id: str
    qty: int
    line_total: Money


class BasketEdit(Schema):
    lines: list[BasketEditLine]


class Stats(Schema):
    sessions: int
    offers: int
    deals: int
    avg_discount_pct: Money
    total_contribution: Money
