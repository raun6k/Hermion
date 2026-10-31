"""WebSocket event schemas (docs/api.md). Mirrored in frontend/lib/types.ts.

Customer events are public: no private fields, same rule as schemas/public.py.
"""

from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import Field, TypeAdapter

from app.schemas.common import AgentState, Money, Schema, SessionStateName
from app.schemas.merchant import MerchantBasket, SessionSummary
from app.schemas.public import BasketLinePublic

# ---- customer -> server -------------------------------------------------------------


class TextInput(Schema):
    type: Literal["text_input"] = "text_input"
    text: str = Field(min_length=1, max_length=1000)


class Mute(Schema):
    type: Literal["mute"] = "mute"
    muted: bool


class LanguagePin(Schema):
    type: Literal["language"] = "language"
    code: str | None


class LanguageSelection(Schema):
    type: Literal["select_language"] = "select_language"
    code: str = Field(min_length=1)


CustomerInbound = Annotated[TextInput | Mute | LanguagePin | LanguageSelection, Field(discriminator="type")]
customer_inbound_adapter: TypeAdapter[CustomerInbound] = TypeAdapter(CustomerInbound)

# ---- server -> customer -------------------------------------------------------------


class StateEvent(Schema):
    type: Literal["state"] = "state"
    state: SessionStateName
    message: str | None = None


class LanguageSelectedEvent(Schema):
    type: Literal["language_selected"] = "language_selected"
    code: str


class AgentStateEvent(Schema):
    type: Literal["agent_state"] = "agent_state"
    state: AgentState


class TranscriptEvent(Schema):
    type: Literal["transcript"] = "transcript"
    speaker: Literal["customer", "hermion"]
    text: str
    final: bool = True


class TtsEnd(Schema):
    type: Literal["tts_end"] = "tts_end"


class TtsStop(Schema):
    type: Literal["tts_stop"] = "tts_stop"


class CaptionEvent(Schema):
    type: Literal["caption"] = "caption"
    speaker: Literal["customer", "hermion"]
    product_name: str | None = None
    amount: Money


class BasketEvent(Schema):
    type: Literal["basket"] = "basket"
    lines: list[BasketLinePublic]
    total: Money


class ErrorEvent(Schema):
    type: Literal["error"] = "error"
    code: str
    message: str


CustomerOutbound = (
    StateEvent
    | LanguageSelectedEvent
    | AgentStateEvent
    | TranscriptEvent
    | TtsEnd
    | TtsStop
    | CaptionEvent
    | BasketEvent
    | ErrorEvent
)
CUSTOMER_OUTBOUND_MODELS: tuple[type[Schema], ...] = CustomerOutbound.__args__  # type: ignore[attr-defined]

# ---- server -> merchant -------------------------------------------------------------


class SessionCreatedEvent(Schema):
    type: Literal["session_created"] = "session_created"
    session: SessionSummary


class SessionStateEvent(Schema):
    type: Literal["session_state"] = "session_state"
    session_id: UUID
    state: SessionStateName


class TraceEvent(Schema):
    type: Literal["trace"] = "trace"
    session_id: UUID
    kind: Literal["message", "offer", "basket", "mandate", "tool_call"]
    data: dict[str, Any]


class DealRequestEvent(Schema):
    type: Literal["deal_request"] = "deal_request"
    session_id: UUID
    basket: MerchantBasket


MerchantOutbound = SessionCreatedEvent | SessionStateEvent | TraceEvent | DealRequestEvent
