"""Customer-facing schemas. MUST NOT contain private fields (target/minimum price, unit cost,
threshold, contribution). tests/api/test_public_schemas.py enforces this."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from app.schemas.common import Money, Schema, SessionStateName


class SessionCreate(Schema):
    qr_token: str
    device_id: str
    customer_name: str | None = Field(default=None, max_length=80)  # optional, asked at scan


class SessionCreated(Schema):
    session_id: UUID


class ShopPublic(Schema):
    """Shown before a session exists: the shop's name and the languages its screens can use."""

    shop_name: str
    languages: list[str]


class MerchantChoice(Schema):
    """Demo shop list: the counter-sign token is public by nature (it is printed on the sign)."""

    merchant_id: str
    shop_name: str
    shop_description: str
    qr_token: str


class SessionPublic(Schema):
    """What the customer pane may know about its session (state, language, the shop's languages)."""

    session_id: UUID
    state: SessionStateName
    language: str | None
    languages: list[str]


class BasketLinePublic(Schema):
    product_id: str
    product_name: str
    qty: int
    line_total: Money
    listed_total: Money  # listed price x qty, so the receipt can show the saving


class BasketPublic(Schema):
    lines: list[BasketLinePublic]
    total: Money


class ConfirmResponse(Schema):
    state: SessionStateName
    basket: BasketPublic


class ExitResponse(Schema):
    state: SessionStateName


class RejoinResponse(Schema):
    state: SessionStateName


class VisitPublic(Schema):
    """One of this device's sessions at a shop, for the customer's home page."""

    session_id: UUID
    state: SessionStateName
    started_at: datetime
    basket: BasketPublic | None = None


class ProductPublic(Schema):
    """What the LLM and the customer may know about a product (search result)."""

    product_id: str
    product_name: str
    category: str
    attributes: dict[str, Any]
    listed_price: Money
    stock_band: Literal["in", "low", "out"]
    negotiable: bool
    # Facts the merchant provided for persuasion; Hermion may cite these and nothing else.
    pitch: str | None = None
    selling_points: list[str] = []
    specs: dict[str, Any] = {}
    best_for: list[str] = []


class ProductForAgent(ProductPublic):
    """Search result for Hermion: the public facts plus the merchant's answers to common objections.
    Never returned on customer routes (the shop page uses ProductPublic)."""

    objection_replies: list[dict[str, str]] = []
