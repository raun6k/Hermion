"""Customer REST (docs/api.md#rest-customer). Responses use schemas.public only."""

from uuid import UUID

from fastapi import APIRouter

from app.api.deps import DbDep, MerchantHubDep
from app.schemas.common import not_implemented
from app.schemas.events import SessionCreatedEvent, SessionStateEvent
from app.schemas.merchant import SessionSummary
from app.schemas.public import ConfirmResponse, ExitResponse, SessionCreate, SessionCreated
from app.services import sessions

router = APIRouter(prefix="/sessions", tags=["customer"])


@router.post("", response_model=SessionCreated, status_code=201)
async def create_session(body: SessionCreate, db: DbDep, hub: MerchantHubDep) -> SessionCreated:
    session = await sessions.create_session(db, body.qr_token, body.device_id)
    await hub.broadcast(SessionCreatedEvent(session=SessionSummary.model_validate(session)))
    return SessionCreated(session_id=session.session_id)


@router.post("/{session_id}/confirm", response_model=ConfirmResponse)
async def confirm(session_id: UUID) -> ConfirmResponse:
    raise not_implemented("Confirm & send")


@router.post("/{session_id}/exit", response_model=ExitResponse)
async def exit_session(session_id: UUID, db: DbDep, hub: MerchantHubDep) -> ExitResponse:
    session = await sessions.exit_session(db, session_id)
    await hub.broadcast(SessionStateEvent(session_id=session.session_id, state=session.state))
    return ExitResponse(state=session.state)
