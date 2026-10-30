"""Shared schema pieces: money, enums, the error envelope."""

from decimal import Decimal
from enum import StrEnum
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, PlainSerializer

from app import languages

# Rupees as Decimal in Python, string on the wire ("850.00").
Money = Annotated[Decimal, PlainSerializer(lambda v: f"{v:.2f}", return_type=str, when_used="json")]


def _language_list(codes: list[str]) -> list[str]:
    if not codes:
        raise ValueError("at least one language is required")
    if len(set(codes)) != len(codes):
        raise ValueError("languages must not repeat")
    for code in codes:
        languages.require(code)
    return codes


# A shop's languages: Sarvam codes from app/languages.py; the first is the merchant's own.
LanguageList = Annotated[list[str], AfterValidator(_language_list)]


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
    field: str | None = None  # set on VALIDATION_ERROR for a single offending input field


class ErrorEnvelope(Schema):
    error: ErrorBody


class AppError(Exception):
    """Raise anywhere; rendered as {"error": {code, message}} with `status`."""

    def __init__(self, code: str, message: str, status: int = 400, field: str | None = None) -> None:
        super().__init__(message)
        self.code, self.message, self.status, self.field = code, message, status, field


def not_implemented(what: str) -> AppError:
    return AppError("NOT_IMPLEMENTED", f"{what} is not implemented yet (walking skeleton)", 501)
