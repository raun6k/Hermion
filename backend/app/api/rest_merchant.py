"""Merchant REST (docs/api.md#rest-merchant). No auth in the MVP."""

import asyncio
from uuid import UUID

from fastapi import APIRouter, Query, Request

from app.agent.briefing import handle_briefing
from app.agent.customer import announce_price_check, resume_customer
from app.api.deps import DbDep, HubsDep, MerchantIdDep
from app.schemas.merchant import (
    BasketEdit,
    BriefingRequest,
    BriefingResponse,
    Goal,
    MandateConfirmResponse,
    MerchantBasket,
    MerchantPatch,
    MerchantProfile,
    PriceCheckAnswer,
    Product,
    ProductCreate,
    ProductPatch,
    ReviewRequest,
    ReviewResponse,
    SessionSummary,
    SessionTrace,
    Stats,
)
from app.services import basket, catalog, mandates, price_checks, sessions, views
from app.services import stats as stats_service

router = APIRouter(prefix="/merchant", tags=["merchant"])


@router.get("", response_model=MerchantProfile)
async def get_profile(db: DbDep, mid: MerchantIdDep) -> MerchantProfile:
    return MerchantProfile.model_validate(await catalog.get_merchant(db, mid))


@router.patch("", response_model=MerchantProfile)
async def patch_profile(body: MerchantPatch, db: DbDep, mid: MerchantIdDep) -> MerchantProfile:
    return MerchantProfile.model_validate(await catalog.patch_merchant(db, body, mid))


@router.get("/products", response_model=list[Product])
async def list_products(db: DbDep, mid: MerchantIdDep) -> list[Product]:
    return [Product.model_validate(p) for p in await catalog.list_products(db, mid)]


@router.post("/products", response_model=Product, status_code=201)
async def create_product(body: ProductCreate, db: DbDep, mid: MerchantIdDep) -> Product:
    return Product.model_validate(await catalog.create_product(db, body, mid))


@router.patch("/products/{product_id}", response_model=Product)
async def patch_product(product_id: str, body: ProductPatch, db: DbDep, mid: MerchantIdDep) -> Product:
    return Product.model_validate(await catalog.patch_product(db, product_id, body, mid))


@router.delete("/products/{product_id}", status_code=204)
async def delete_product(product_id: str, db: DbDep, mid: MerchantIdDep) -> None:
    await catalog.delete_product(db, product_id, mid)


@router.get("/goals", response_model=list[Goal])
async def list_goals(db: DbDep, mid: MerchantIdDep) -> list[Goal]:
    return [Goal.model_validate(g) for g in await catalog.list_goals(db, mid)]


@router.put("/goals", response_model=list[Goal])
async def replace_goals(body: list[Goal], db: DbDep, mid: MerchantIdDep) -> list[Goal]:
    return [Goal.model_validate(g) for g in await catalog.replace_goals(db, body, mid)]


@router.get("/sessions", response_model=list[SessionSummary])
async def list_sessions(
    db: DbDep, mid: MerchantIdDep, scope: str = Query("live", pattern="^(live|past)$")
) -> list[SessionSummary]:
    return await views.list_summaries(db, scope, mid)


@router.get("/sessions/{session_id}", response_model=SessionTrace)
async def get_trace(session_id: UUID, db: DbDep) -> SessionTrace:
    return await views.session_trace(db, session_id)


@router.post("/sessions/{session_id}/review", response_model=ReviewResponse)
async def review(
    session_id: UUID, body: ReviewRequest, request: Request, db: DbDep, hubs: HubsDep
) -> ReviewResponse:
    async with request.app.state.turn_locks.setdefault(session_id, asyncio.Lock()):
        session = await basket.review(db, hubs, session_id, body.action)
        return ReviewResponse(state=session.state)


@router.post("/sessions/{session_id}/briefing", response_model=BriefingResponse)
async def briefing(
    session_id: UUID, body: BriefingRequest, request: Request, db: DbDep, hubs: HubsDep
) -> BriefingResponse:
    lock = request.app.state.turn_locks.setdefault(session_id, asyncio.Lock())
    async with lock:
        return await handle_briefing(db, hubs, request.app.state.llm, session_id, body.text)


@router.post("/sessions/{session_id}/mandates/{mandate_id}/confirm", response_model=MandateConfirmResponse)
async def confirm_mandate(
    session_id: UUID, mandate_id: UUID, request: Request, db: DbDep, hubs: HubsDep
) -> MandateConfirmResponse:
    async with request.app.state.turn_locks.setdefault(session_id, asyncio.Lock()):
        state = await mandates.confirm(db, hubs, session_id, mandate_id)
        await resume_customer(db, hubs, request.app.state.llm, session_id)
        return MandateConfirmResponse(state=state)


@router.put("/sessions/{session_id}/basket", response_model=MerchantBasket)
async def edit_basket(
    session_id: UUID, body: BasketEdit, request: Request, db: DbDep, hubs: HubsDep
) -> MerchantBasket:
    async with request.app.state.turn_locks.setdefault(session_id, asyncio.Lock()):
        return await basket.edit_in_person(db, hubs, session_id, body.lines)


@router.get("/stats", response_model=Stats)
async def stats(db: DbDep, mid: MerchantIdDep, days: int | None = Query(None, ge=1, le=365)) -> Stats:
    return await stats_service.merchant_stats(db, mid, days)


@router.post("/sessions/{session_id}/price-check", response_model=ReviewResponse)
async def answer_price_check(
    session_id: UUID, body: PriceCheckAnswer, request: Request, db: DbDep, hubs: HubsDep
) -> ReviewResponse:
    """Accept, counter or decline Hermion's question about one close offer."""
    async with request.app.state.turn_locks.setdefault(session_id, asyncio.Lock()):
        action, offer = await price_checks.answer(db, hubs, session_id, body.action, body.price)
        await announce_price_check(db, hubs, request.app.state.llm, session_id, action, offer)
        return ReviewResponse(state=(await sessions.get_session(db, session_id)).state)
