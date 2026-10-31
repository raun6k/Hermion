"""Merchant-facing schemas (may contain private fields). Never use on customer routes."""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import Field, model_validator

from app import languages
from app.schemas.common import LanguageList, Money, Schema, SessionStateName


class MerchantProfile(Schema):
    merchant_id: str
    shop_name: str
    shop_description: str
    # Every language the app can speak; not merchant-edited (docs/data.md). PATCH still accepts it until
    # the settings UI drops the field.
    languages: LanguageList = Field(default_factory=lambda: list(languages.LANGUAGES))
    negotiation_instructions: str
    qr_token: str
    escalation: Literal["never", "serious", "rare", "when_close"] = "serious"
    escalation_gap_pct: int = Field(default=5, ge=0, le=50)


class MerchantPatch(Schema):
    shop_name: str | None = None
    shop_description: str | None = None
    languages: LanguageList | None = None
    negotiation_instructions: str | None = None
    escalation: Literal["never", "serious", "rare", "when_close"] | None = None
    escalation_gap_pct: int | None = Field(default=None, ge=0, le=50)


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
    pitch: str | None = None
    selling_points: list[str] | None = None
    specs: dict[str, Any] | None = None
    best_for: list[str] | None = None
    objection_replies: list[dict[str, str]] | None = None
    pairs_with_ids: list[str] | None = None
    upsell_ids: list[str] | None = None


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
    pitch: str | None = None
    selling_points: list[str] | None = None
    specs: dict[str, Any] | None = None
    best_for: list[str] | None = None
    objection_replies: list[dict[str, str]] | None = None
    pairs_with_ids: list[str] | None = None
    upsell_ids: list[str] | None = None


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
    customer_name: str | None = None
    display_name: str = ""  # the name, or "Guest N" in start order for this shop
    price_check: dict[str, Any] | None = None  # open shopkeeper price check, if any


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
    profile: str | None = None
    headroom: str | None = None
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
    # Links a tool call to its `offers` row (offers.id) so the trace view can show them together.
    evaluation_id: str | None = None

    @model_validator(mode="after")
    def _link_evaluation(self) -> "TraceToolCall":
        if self.evaluation_id is None:
            self.evaluation_id = self.result.get("evaluation_id") or self.arguments.get("evaluation_id")
        return self


class TraceStateChange(Schema):
    id: UUID
    from_state: str
    to_state: str
    created_at: datetime


class TraceTiming(Schema):
    id: UUID
    message_id: UUID
    measurements: dict[str, Any]
    created_at: datetime


class SessionTrace(Schema):
    session: SessionSummary
    messages: list[TraceMessage]
    offers: list[TraceOffer]
    tool_calls: list[TraceToolCall]
    state_changes: list[TraceStateChange]
    turn_timings: list[TraceTiming]
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


class PriceCheckAnswer(Schema):
    action: Literal["accept", "counter", "decline"]
    price: Money | None = None  # whole rupees for the whole evaluation; required for `counter`


class BasketEditLine(Schema):
    product_id: str
    qty: int
    line_total: Money


class BasketEdit(Schema):
    lines: list[BasketEditLine]


class DayPoint(Schema):
    day: str  # YYYY-MM-DD
    deals: int
    revenue: Money


class NamedCount(Schema):
    name: str
    value: int


class TopProduct(Schema):
    product_id: str
    product_name: str
    units: int
    revenue: Money


class Funnel(Schema):
    scanned: int
    started: int
    offered: int
    in_basket: int
    confirmed: int
    accepted: int


class Stats(Schema):
    sessions: int
    offers: int
    deals: int
    avg_discount_pct: Money
    total_contribution: Money
    days: int | None = None  # window the figures cover; None = all time
    revenue_won: Money = Decimal(0)
    discount_given: Money = Decimal(0)  # listed minus agreed on accepted baskets
    funnel: Funnel | None = None
    per_day: list[DayPoint] = Field(default_factory=list)
    top_products: list[TopProduct] = Field(default_factory=list)
    language_mix: list[NamedCount] = Field(default_factory=list)
    upsell_attach_rate: Decimal = Decimal(0)  # share of accepted deals with a suggested add-on in the basket
    abandoned_baskets: int = 0
    escalation_rate: Decimal = Decimal(0)  # share of sessions where Hermion asked the shopkeeper
    total_negotiation_seconds: int = 0  # average per finished session
    avg_response_ms: int | None = None  # average agent time per turn; None when unmeasured
    # How sessions ended: accepted | declined (by the shop) | exited (customer left) | open (still going).
    outcomes: list[NamedCount] = Field(default_factory=list)
    # Sessions started per hour of the day, in UTC (`name` is "0".."23"); the dashboard shows local time.
    per_hour_utc: list[NamedCount] = Field(default_factory=list)
