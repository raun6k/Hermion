"""Merchant profile, products, goals; product search (RapidFuzz, later)."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Merchant, Product
from app.schemas.common import AppError

# No auth in the MVP: one seeded merchant (docs/api.md).
MERCHANT_ID = "M001"


async def get_merchant(db: AsyncSession) -> Merchant:
    merchant = await db.get(Merchant, MERCHANT_ID)
    if merchant is None:
        raise AppError("MERCHANT_NOT_SEEDED", "Run `make seed` first", 503)
    return merchant


async def list_products(db: AsyncSession) -> list[Product]:
    rows = await db.scalars(
        select(Product).where(Product.merchant_id == MERCHANT_ID).order_by(Product.product_id)
    )
    return list(rows)


async def search_products(db: AsyncSession, query: str) -> list[Product]:
    raise NotImplementedError
