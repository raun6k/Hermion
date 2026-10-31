"""Customer REST (docs/api.md#rest-customer). Responses use schemas.public only."""

import asyncio
from uuid import UUID

from fastapi import APIRouter, Request, Response
from sqlalchemy import select

from app.agent.customer import welcome_back
from app.api.deps import DbDep, HubsDep, MerchantHubDep
from app.db.models import Merchant, Session
from app.schemas.common import AppError
from app.schemas.events import SessionCreatedEvent
from app.schemas.merchant import SessionSummary
from app.schemas.public import (
    BasketPublic,
    ConfirmResponse,
    ExitResponse,
    MerchantChoice,
    ProductPublic,
    RejoinResponse,
    SessionCreate,
    SessionCreated,
    SessionPublic,
    ShopPublic,
    VisitPublic,
)
from app.services import basket, catalog, sessions, views

router = APIRouter(prefix="/sessions", tags=["customer"])
shop_router = APIRouter(tags=["customer"])


@shop_router.get("/merchants", response_model=list[MerchantChoice])
async def merchants(db: DbDep) -> list[MerchantChoice]:
    """Demo-only: the shops the dashboard's avatar menu can switch between."""
    return [MerchantChoice.model_validate(m) for m in await catalog.list_merchants(db)]


@shop_router.get("/shop/products", response_model=list[ProductPublic])
async def shop_products(db: DbDep, qr_token: str | None = None) -> list[ProductPublic]:
    """Up to six in-stock products with their persuasion facts, for the shop page (public fields only): one
    per product name (sizes are variants of one product), a different category first for variety."""
    merchant = await catalog.get_merchant(db)
    if qr_token:
        merchant = await db.scalar(select(Merchant).where(Merchant.qr_token == qr_token)) or merchant
    unique = {}
    for p in await catalog.list_products(db, merchant.merchant_id):
        if p.available_stock > 0 and (p.pitch or p.selling_points):
            unique.setdefault(p.product_name, p)
    seen: set[str] = set()
    varied = [p for p in unique.values() if not (p.category in seen or seen.add(p.category))]
    varied += [p for p in unique.values() if p not in varied]
    return [catalog.to_public(p) for p in varied[:6]]


@shop_router.get("/shop", response_model=ShopPublic)
async def shop(db: DbDep, qr_token: str | None = None) -> ShopPublic:
    merchant = await catalog.get_merchant(db)
    if qr_token:
        found = await db.scalar(select(Merchant).where(Merchant.qr_token == qr_token))
        merchant = found or merchant
    return ShopPublic(shop_name=merchant.shop_name, languages=merchant.languages)


@router.post("", response_model=SessionCreated, status_code=201)
async def create_session(
    body: SessionCreate, response: Response, db: DbDep, hub: MerchantHubDep
) -> SessionCreated:
    session, created = await sessions.get_or_create_session(
        db, body.qr_token, body.device_id, (body.customer_name or "").strip() or None
    )
    if created:
        await hub.broadcast(SessionCreatedEvent(session=SessionSummary.model_validate(session)))
    else:
        response.status_code = 200  # resumed the device's live session at this shop
    return SessionCreated(session_id=session.session_id)


@router.get("/visits", response_model=list[VisitPublic])
async def visits(qr_token: str, device_id: str, db: DbDep) -> list[VisitPublic]:
    """This device's last five sessions at the shop, newest first, for the customer's home page."""
    merchant = await db.scalar(select(Merchant).where(Merchant.qr_token == qr_token))
    if merchant is None:
        raise AppError("UNKNOWN_QR", "This QR code does not belong to a Hermion shop", 404)
    rows = await db.scalars(
        select(Session)
        .where(Session.merchant_id == merchant.merchant_id, Session.device_id == device_id)
        .order_by(Session.started_at.desc())
        .limit(5)
    )
    out = []
    for s in rows:
        basket = await views.public_basket(db, s.session_id)
        out.append(
            VisitPublic(
                session_id=s.session_id,
                state=s.state,
                started_at=s.started_at,
                basket=basket if basket.lines else None,
            )
        )
    return out


@router.post("/{session_id}/rejoin", response_model=RejoinResponse)
async def rejoin(session_id: UUID, request: Request, db: DbDep, hubs: HubsDep) -> RejoinResponse:
    """Talk to Hermion again. A basket waiting for the shop comes back to the customer, and Hermion opens
    with a short status and asks how it can help (call once the customer socket is open, so it is spoken)."""
    async with request.app.state.turn_locks.setdefault(session_id, asyncio.Lock()):
        session, withdrawn = await sessions.rejoin(db, hubs, session_id)
        if withdrawn:
            await welcome_back(db, hubs, request.app.state.llm, session_id)
        return RejoinResponse(state=session.state)


@router.delete("/{session_id}/basket/{product_id}", response_model=BasketPublic)
async def remove_from_basket(session_id: UUID, product_id: str, db: DbDep, hubs: HubsDep) -> BasketPublic:
    """The receipt page's Remove button (same service the voice tool uses)."""
    return await basket.remove(db, hubs, session_id, product_id)


@router.get("/{session_id}", response_model=SessionPublic)
async def get_session(session_id: UUID, db: DbDep) -> SessionPublic:
    session = await sessions.get_session(db, session_id)
    merchant = await catalog.get_merchant(db, session.merchant_id)
    return SessionPublic(
        session_id=session.session_id,
        state=session.state,
        language=session.language,
        languages=merchant.languages,
    )


@router.post("/{session_id}/confirm", response_model=ConfirmResponse)
async def confirm(session_id: UUID, request: Request, db: DbDep, hubs: HubsDep) -> ConfirmResponse:
    async with request.app.state.turn_locks.setdefault(session_id, asyncio.Lock()):
        session, public = await basket.confirm(db, hubs, session_id)
        return ConfirmResponse(state=session.state, basket=public)


@router.post("/{session_id}/exit", response_model=ExitResponse)
async def exit_session(session_id: UUID, request: Request, db: DbDep, hubs: HubsDep) -> ExitResponse:
    async with request.app.state.turn_locks.setdefault(session_id, asyncio.Lock()):
        session = await sessions.exit_session(db, hubs, session_id)
        return ExitResponse(state=session.state)
