"""Customer REST (docs/api.md#rest-customer). Responses use schemas.public only."""

from uuid import UUID

from fastapi import APIRouter

from app.api.deps import DbDep, HubsDep, MerchantHubDep
from app.schemas.events import SessionCreatedEvent
from app.schemas.merchant import SessionSummary
from app.schemas.public import ConfirmResponse, ExitResponse, SessionCreate, SessionCreated, SessionPublic
from app.services import basket, catalog, sessions

router = APIRouter(prefix="/sessions", tags=["customer"])


@router.post("", response_model=SessionCreated, status_code=201)
async def create_session(body: SessionCreate, db: DbDep, hub: MerchantHubDep) -> SessionCreated:
    session = await sessions.create_session(db, body.qr_token, body.device_id)
    await hub.broadcast(SessionCreatedEvent(session=SessionSummary.model_validate(session)))
    return SessionCreated(session_id=session.session_id)


@router.get("/{session_id}", response_model=SessionPublic)
async def get_session(session_id: UUID, db: DbDep) -> SessionPublic:
    session = await sessions.get_session(db, session_id)
    merchant = await catalog.get_merchant(db)
    return SessionPublic(
        session_id=session.session_id,
        state=session.state,
        language=session.language,
        languages=merchant.languages,
    )


@router.post("/{session_id}/confirm", response_model=ConfirmResponse)
async def confirm(session_id: UUID, db: DbDep, hubs: HubsDep) -> ConfirmResponse:
    session, public = await basket.confirm(db, hubs, session_id)
    return ConfirmResponse(state=session.state, basket=public)


@router.post("/{session_id}/exit", response_model=ExitResponse)
async def exit_session(session_id: UUID, db: DbDep, hubs: HubsDep) -> ExitResponse:
    session = await sessions.exit_session(db, hubs, session_id)
    return ExitResponse(state=session.state)
