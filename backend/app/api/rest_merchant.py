"""Merchant REST (docs/api.md#rest-merchant). No auth in the MVP."""

from uuid import UUID

from fastapi import APIRouter, Query

from app.api.deps import DbDep
from app.schemas.common import not_implemented
from app.schemas.merchant import (
    BasketEdit,
    BriefingRequest,
    BriefingResponse,
    Goal,
    MerchantPatch,
    MerchantProfile,
    Product,
    ProductCreate,
    ProductPatch,
    ReviewRequest,
    SessionSummary,
    SessionTrace,
    Stats,
)
from app.services import catalog

router = APIRouter(prefix="/merchant", tags=["merchant"])


@router.get("", response_model=MerchantProfile)
async def get_profile(db: DbDep) -> MerchantProfile:
    return MerchantProfile.model_validate(await catalog.get_merchant(db))


@router.patch("", response_model=MerchantProfile)
async def patch_profile(body: MerchantPatch) -> MerchantProfile:
    raise not_implemented("Shop settings edit")


@router.get("/products", response_model=list[Product])
async def list_products(db: DbDep) -> list[Product]:
    return [Product.model_validate(p) for p in await catalog.list_products(db)]


@router.post("/products", response_model=Product, status_code=201)
async def create_product(body: ProductCreate) -> Product:
    raise not_implemented("Product create")


@router.patch("/products/{product_id}", response_model=Product)
async def patch_product(product_id: str, body: ProductPatch) -> Product:
    raise not_implemented("Product edit")


@router.delete("/products/{product_id}", status_code=204)
async def delete_product(product_id: str) -> None:
    raise not_implemented("Product delete")


@router.get("/goals", response_model=list[Goal])
async def list_goals() -> list[Goal]:
    raise not_implemented("Goals")


@router.put("/goals", response_model=list[Goal])
async def replace_goals(body: list[Goal]) -> list[Goal]:
    raise not_implemented("Goals")


@router.get("/sessions", response_model=list[SessionSummary])
async def list_sessions(scope: str = Query("live", pattern="^(live|past)$")) -> list[SessionSummary]:
    raise not_implemented("Session list")


@router.get("/sessions/{session_id}", response_model=SessionTrace)
async def get_trace(session_id: UUID) -> SessionTrace:
    raise not_implemented("Session trace")


@router.post("/sessions/{session_id}/review")
async def review(session_id: UUID, body: ReviewRequest) -> None:
    raise not_implemented("Basket review")


@router.post("/sessions/{session_id}/briefing", response_model=BriefingResponse)
async def briefing(session_id: UUID, body: BriefingRequest) -> BriefingResponse:
    raise not_implemented("Briefing")


@router.post("/sessions/{session_id}/mandates/{mandate_id}/confirm")
async def confirm_mandate(session_id: UUID, mandate_id: UUID) -> None:
    raise not_implemented("Mandate confirm")


@router.put("/sessions/{session_id}/basket")
async def edit_basket(session_id: UUID, body: BasketEdit) -> None:
    raise not_implemented("In-person basket edit")


@router.get("/stats", response_model=Stats)
async def stats() -> Stats:
    raise not_implemented("Stats")
