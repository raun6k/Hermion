"""Customer-facing schemas. MUST NOT contain private fields (target/minimum price, unit cost,
threshold, contribution). tests/api/test_public_schemas.py enforces this."""

from typing import Any, Literal
from uuid import UUID

from app.schemas.common import Money, Schema, SessionStateName


class SessionCreate(Schema):
    qr_token: str
    device_id: str


class SessionCreated(Schema):
    session_id: UUID


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


class BasketPublic(Schema):
    lines: list[BasketLinePublic]
    total: Money


class ConfirmResponse(Schema):
    state: SessionStateName
    basket: BasketPublic


class ExitResponse(Schema):
    state: SessionStateName


class ProductPublic(Schema):
    """What the LLM and the customer may know about a product (search result)."""

    product_id: str
    product_name: str
    category: str
    attributes: dict[str, Any]
    listed_price: Money
    stock_band: Literal["in", "low", "out"]
    negotiable: bool
