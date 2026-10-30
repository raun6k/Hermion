"""Merchant REST (docs/api.md#rest-merchant). No auth in the MVP."""

from uuid import UUID

from fastapi import APIRouter, Query

from app.api.deps import DbDep, HubsDep
from app.schemas.common import not_implemented
from app.schemas.merchant import (
    BasketEdit,
    BriefingRequest,
    BriefingResponse,
    Goal,
    MandateConfirmResponse,
    MerchantBasket,
    MerchantPatch,
    MerchantProfile,
    Product,
    ProductCreate,
    ProductPatch,
    ReviewRequest,
    ReviewResponse,
    SessionSummary,
    SessionTrace,
    Stats,
)
from app.services import basket, catalog, mandates, views

router = APIRouter(prefix="/merchant", tags=["merchant"])


@router.get("", response_model=MerchantProfile)
async def get_profile(db: DbDep) -> MerchantProfile:
    return MerchantProfile.model_validate(await catalog.get_merchant(db))


@router.patch("", response_model=MerchantProfile)
async def patch_profile(body: MerchantPatch, db: DbDep) -> MerchantProfile:
    return MerchantProfile.model_validate(await catalog.patch_merchant(db, body))


@router.get("/products", response_model=list[Product])
async def list_products(db: DbDep) -> list[Product]:
    return [Product.model_validate(p) for p in await catalog.list_products(db)]


@router.post("/products", response_model=Product, status_code=201)
async def create_product(body: ProductCreate, db: DbDep) -> Product:
    return Product.model_validate(await catalog.create_product(db, body))


@router.patch("/products/{product_id}", response_model=Product)
async def patch_product(product_id: str, body: ProductPatch, db: DbDep) -> Product:
    return Product.model_validate(await catalog.patch_product(db, product_id, body))


@router.delete("/products/{product_id}", status_code=204)
async def delete_product(product_id: str, db: DbDep) -> None:
    await catalog.delete_product(db, product_id)


@router.get("/goals", response_model=list[Goal])
async def list_goals(db: DbDep) -> list[Goal]:
    return [Goal.model_validate(g) for g in await catalog.list_goals(db)]


@router.put("/goals", response_model=list[Goal])
async def replace_goals(body: list[Goal], db: DbDep) -> list[Goal]:
    return [Goal.model_validate(g) for g in await catalog.replace_goals(db, body)]


@router.get("/sessions", response_model=list[SessionSummary])
async def list_sessions(
    db: DbDep, scope: str = Query("live", pattern="^(live|past)$")
) -> list[SessionSummary]:
    return await views.list_summaries(db, scope)


@router.get("/sessions/{session_id}", response_model=SessionTrace)
async def get_trace(session_id: UUID, db: DbDep) -> SessionTrace:
    return await views.session_trace(db, session_id)


@router.post("/sessions/{session_id}/review", response_model=ReviewResponse)
async def review(session_id: UUID, body: ReviewRequest, db: DbDep, hubs: HubsDep) -> ReviewResponse:
    session = await basket.review(db, hubs, session_id, body.action)
    return ReviewResponse(state=session.state)


@router.post("/sessions/{session_id}/briefing", response_model=BriefingResponse)
async def briefing(session_id: UUID, body: BriefingRequest) -> BriefingResponse:
    raise not_implemented("Briefing")  # Stage 2: agent/briefing.py


@router.post("/sessions/{session_id}/mandates/{mandate_id}/confirm", response_model=MandateConfirmResponse)
async def confirm_mandate(
    session_id: UUID, mandate_id: UUID, db: DbDep, hubs: HubsDep
) -> MandateConfirmResponse:
    return MandateConfirmResponse(state=await mandates.confirm(db, hubs, session_id, mandate_id))


@router.put("/sessions/{session_id}/basket", response_model=MerchantBasket)
async def edit_basket(session_id: UUID, body: BasketEdit, db: DbDep, hubs: HubsDep) -> MerchantBasket:
    return await basket.edit_in_person(db, hubs, session_id, body.lines)


@router.get("/stats", response_model=Stats)
async def stats() -> Stats:
    raise not_implemented("Stats")  # Stage 3
