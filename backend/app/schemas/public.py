"""Customer-facing schemas. MUST NOT contain private fields (target/minimum price, unit cost,
threshold, contribution). tests/api/test_public_schemas.py enforces this."""

from uuid import UUID

from app.schemas.common import Money, Schema, SessionStateName


class SessionCreate(Schema):
    qr_token: str
    device_id: str


class SessionCreated(Schema):
    session_id: UUID


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
