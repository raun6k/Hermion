"""Load backend/seed/ into the database (idempotent: replaces the seeded merchant's data).

Run: `uv run python -m app.seed`
"""

import asyncio
import csv
import json
import logging
from decimal import Decimal
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import DatabaseSettings
from app.db.models import (
    BasketLine,
    Goal,
    Mandate,
    Merchant,
    Message,
    Offer,
    Product,
    Session,
    StateChange,
    ToolCallTrace,
    TurnTiming,
)
from app.schemas.merchant import MerchantProfile

SEED_DIR = Path(__file__).resolve().parents[1] / "seed"
log = logging.getLogger("seed")


def _money(value: str) -> Decimal | None:
    return Decimal(value) if value.strip() else None


def _json(row: dict[str, str], key: str):
    raw = (row.get(key) or "").strip()
    return json.loads(raw) if raw else None


def load_products(path: Path) -> list[Product]:
    with path.open(newline="", encoding="utf-8") as f:
        return [
            Product(
                product_id=row["product_id"],
                merchant_id=row["merchant_id"],
                product_name=row["product_name"],
                category=row["category"],
                attributes=json.loads(row["attributes"] or "{}"),
                aliases=[a for a in row["aliases"].split("|") if a],
                listed_price=Decimal(row["listed_price"]),
                target_price=_money(row["target_price"]),
                minimum_price=Decimal(row["minimum_price"]),
                unit_cost=Decimal(row["unit_cost"]),
                available_stock=int(row["available_stock"]),
                negotiable=row["negotiable"].strip().lower() == "true",
                pitch=(row.get("pitch") or "").strip() or None,
                selling_points=_json(row, "selling_points"),
                specs=_json(row, "specs"),
                best_for=_json(row, "best_for"),
                objection_replies=_json(row, "objection_replies"),
                pairs_with_ids=_json(row, "pairs_with_ids"),
                upsell_ids=_json(row, "upsell_ids"),
            )
            for row in csv.DictReader(f)
        ]


async def seed_merchant(db: AsyncSession, shop_dir: Path) -> str:
    profile = MerchantProfile.model_validate_json((shop_dir / "merchant.json").read_text(encoding="utf-8"))
    merchant = Merchant(**profile.model_dump())
    goals = [Goal(**g) for g in json.loads((shop_dir / "goals.json").read_text(encoding="utf-8"))]
    products = load_products(shop_dir / "products.csv")

    # Children first: wipe everything belonging to this merchant, then insert fresh.
    merchant_sessions = select(Session.session_id).where(Session.merchant_id == merchant.merchant_id)
    for model in (BasketLine, Offer, Mandate, TurnTiming, Message, ToolCallTrace, StateChange):
        await db.execute(delete(model).where(model.session_id.in_(merchant_sessions)))
    await db.execute(delete(Session).where(Session.merchant_id == merchant.merchant_id))
    await db.execute(delete(Goal).where(Goal.merchant_id == merchant.merchant_id))
    await db.execute(delete(Product).where(Product.merchant_id == merchant.merchant_id))
    await db.execute(delete(Merchant).where(Merchant.merchant_id == merchant.merchant_id))
    await db.flush()

    db.add(merchant)
    await db.flush()
    db.add_all([*products, *goals])
    merchant_id = merchant.merchant_id
    await db.commit()
    log.info("seeded merchant=%s products=%d goals=%d", merchant_id, len(products), len(goals))
    return merchant_id


async def seed(db: AsyncSession, seed_dir: Path = SEED_DIR) -> None:
    """Load every shop under `seed_dir/merchants/<slug>/` (merchant.json, products.csv, goals.json)."""
    for shop_dir in sorted((seed_dir / "merchants").iterdir()):
        if shop_dir.is_dir():
            await seed_merchant(db, shop_dir)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    engine = create_async_engine(DatabaseSettings().database_url)
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        await seed(db)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
