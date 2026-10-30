"""Shared schema pieces: money, enums, the error envelope."""

from decimal import Decimal
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, PlainSerializer

# Rupees as Decimal in Python, string on the wire ("850.00").
Money = Annotated[Decimal, PlainSerializer(lambda v: f"{v:.2f}", return_type=str, when_used="json")]


class Schema(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class SessionStateName(StrEnum):
    intro = "intro"
    discovery = "discovery"
    negotiating = "negotiating"
    pending_merchant = "pending_merchant"
    briefing = "briefing"
    in_person = "in_person"
    accepted = "accepted"
    declined = "declined"
    exited = "exited"


class AgentState(StrEnum):
    idle = "idle"
    listening = "listening"
    thinking = "thinking"
    speaking = "speaking"
    happy = "happy"
    negotiating = "negotiating"


class ErrorBody(Schema):
    code: str
    message: str


class ErrorEnvelope(Schema):
    error: ErrorBody


class AppError(Exception):
    """Raise anywhere; rendered as {"error": {code, message}} with `status`."""

    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def not_implemented(what: str) -> AppError:
    return AppError("NOT_IMPLEMENTED", f"{what} is not implemented yet (walking skeleton)", 501)
