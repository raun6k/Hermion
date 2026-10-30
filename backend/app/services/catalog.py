"""Merchant profile, products, goals; product search (RapidFuzz over names, attributes, aliases)."""

from decimal import Decimal

from rapidfuzz import fuzz, utils
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BasketLine, Goal, Merchant, Product
from app.engine.types import ProductTerms
from app.schemas.common import AppError
from app.schemas.merchant import Goal as GoalSchema
from app.schemas.merchant import MerchantPatch, ProductCreate, ProductPatch
from app.schemas.public import ProductPublic

# No auth in the MVP: one seeded merchant (docs/api.md).
MERCHANT_ID = "M001"
LOW_STOCK_MAX = 3
SEARCH_LIMIT = 5
SEARCH_MIN_SCORE = 60


async def get_merchant(db: AsyncSession) -> Merchant:
    merchant = await db.get(Merchant, MERCHANT_ID)
    if merchant is None:
        raise AppError("MERCHANT_NOT_SEEDED", "Run `make seed` first", 503)
    return merchant


async def patch_merchant(db: AsyncSession, patch: MerchantPatch) -> Merchant:
    merchant = await get_merchant(db)
    for field, value in patch.model_dump(exclude_unset=True).items():
        if value is None:
            raise AppError("VALIDATION_ERROR", f"{field} cannot be empty", 422, field)
        setattr(merchant, field, value)
    await db.commit()
    return merchant


# ---- products ---------------------------------------------------------------------


async def list_products(db: AsyncSession) -> list[Product]:
    rows = await db.scalars(
        select(Product).where(Product.merchant_id == MERCHANT_ID).order_by(Product.product_id)
    )
    return list(rows)


async def get_product(db: AsyncSession, product_id: str) -> Product:
    product = await db.get(Product, product_id)
    if product is None or product.merchant_id != MERCHANT_ID:
        raise AppError("PRODUCT_NOT_FOUND", f"Unknown product {product_id}", 404)
    return product


def _whole(value: Decimal, field: str) -> None:
    if value != value.to_integral_value():
        raise AppError("VALIDATION_ERROR", f"{field} must be a whole number of rupees", 422, field)


def validate_prices(
    listed: Decimal, target: Decimal | None, minimum: Decimal, cost: Decimal, stock: int
) -> None:
    """0 < minimum <= target <= listed, whole rupees, cost >= 0, stock >= 0 (docs/api.md)."""
    if minimum <= 0:
        raise AppError("VALIDATION_ERROR", "Minimum price must be above 0", 422, "minimum_price")
    if minimum > listed:
        raise AppError(
            "VALIDATION_ERROR", "Minimum price cannot exceed the listed price", 422, "minimum_price"
        )
    if target is not None and not minimum <= target <= listed:
        raise AppError(
            "VALIDATION_ERROR", "Target price must be between minimum and listed price", 422, "target_price"
        )
    if cost < 0:
        raise AppError("VALIDATION_ERROR", "Unit cost cannot be negative", 422, "unit_cost")
    if stock < 0:
        raise AppError("VALIDATION_ERROR", "Stock cannot be negative", 422, "available_stock")
    _whole(listed, "listed_price")
    _whole(minimum, "minimum_price")
    if target is not None:
        _whole(target, "target_price")


async def create_product(db: AsyncSession, body: ProductCreate) -> Product:
    if await db.get(Product, body.product_id) is not None:
        raise AppError("PRODUCT_EXISTS", f"{body.product_id} already exists", 409, "product_id")
    validate_prices(
        body.listed_price, body.target_price, body.minimum_price, body.unit_cost, body.available_stock
    )
    product = Product(merchant_id=MERCHANT_ID, **body.model_dump())
    db.add(product)
    await db.commit()
    return product


async def patch_product(db: AsyncSession, product_id: str, patch: ProductPatch) -> Product:
    product = await get_product(db, product_id)
    changes = patch.model_dump(exclude_unset=True)
    for field in (
        "product_name",
        "category",
        "listed_price",
        "minimum_price",
        "unit_cost",
        "available_stock",
    ):
        if field in changes and changes[field] is None:
            raise AppError("VALIDATION_ERROR", f"{field} cannot be empty", 422, field)
    merged = {
        "listed_price": product.listed_price,
        "target_price": product.target_price,
        "minimum_price": product.minimum_price,
        "unit_cost": product.unit_cost,
        "available_stock": product.available_stock,
    } | {
        k: v
        for k, v in changes.items()
        if k in {"listed_price", "target_price", "minimum_price", "unit_cost", "available_stock"}
    }
    validate_prices(
        merged["listed_price"],
        merged["target_price"],
        merged["minimum_price"],
        merged["unit_cost"],
        merged["available_stock"],
    )
    for field, value in changes.items():
        setattr(product, field, value)
    await db.commit()
    return product


async def delete_product(db: AsyncSession, product_id: str) -> None:
    product = await get_product(db, product_id)
    in_baskets = await db.scalar(select(BasketLine.id).where(BasketLine.product_id == product_id).limit(1))
    if in_baskets is not None:
        raise AppError(
            "PRODUCT_IN_USE", "This product appears in customer baskets; set stock to 0 instead", 409
        )
    for goal in await db.scalars(select(Goal).where(Goal.merchant_id == MERCHANT_ID)):
        if product_id in goal.product_ids:
            goal.product_ids = [p for p in goal.product_ids if p != product_id]
    await db.delete(product)
    await db.commit()


def terms(product: Product) -> ProductTerms:
    return ProductTerms(
        product_id=product.product_id,
        listed_price=product.listed_price,
        target_price=product.target_price,
        minimum_price=product.minimum_price,
        available_stock=product.available_stock,
        negotiable=product.negotiable,
    )


async def product_terms(db: AsyncSession, product_ids: list[str]) -> dict[str, ProductTerms]:
    rows = await db.scalars(select(Product).where(Product.product_id.in_(product_ids)))
    return {p.product_id: terms(p) for p in rows}


# ---- search -----------------------------------------------------------------------


def stock_band(stock: int) -> str:
    return "out" if stock <= 0 else "low" if stock <= LOW_STOCK_MAX else "in"


def to_public(product: Product) -> ProductPublic:
    return ProductPublic(
        product_id=product.product_id,
        product_name=product.product_name,
        category=product.category,
        attributes=product.attributes,
        listed_price=product.listed_price,
        stock_band=stock_band(product.available_stock),  # type: ignore[arg-type]
        negotiable=product.negotiable,
    )


def _document(product: Product) -> str:
    attrs = " ".join(str(v) for v in product.attributes.values())
    return f"{product.product_name} {product.category} {attrs} {' '.join(product.aliases)}"


def rank_products(products: list[Product], query: str) -> list[Product]:
    """Fuzzy match over names, attributes and aliases; in-stock variants first among equal scores."""
    scored: list[tuple[float, bool, str, Product]] = []
    for p in products:
        score = max(
            fuzz.token_set_ratio(query, _document(p), processor=utils.default_process),
            *(
                fuzz.WRatio(query, text, processor=utils.default_process) * 0.95
                for text in [p.product_name, *p.aliases]
            ),
        )
        if score >= SEARCH_MIN_SCORE:
            scored.append((score, p.available_stock > 0, p.product_id, p))
    scored.sort(key=lambda t: (-t[0], not t[1], t[2]))
    return [p for *_, p in scored[:SEARCH_LIMIT]]


async def search_products(db: AsyncSession, query: str) -> list[ProductPublic]:
    query = query.strip()
    if not query:
        return []
    return [to_public(p) for p in rank_products(await list_products(db), query)]


# ---- goals ------------------------------------------------------------------------


async def list_goals(db: AsyncSession) -> list[Goal]:
    rows = await db.scalars(select(Goal).where(Goal.merchant_id == MERCHANT_ID).order_by(Goal.goal_id))
    return list(rows)


async def replace_goals(db: AsyncSession, goals: list[GoalSchema]) -> list[Goal]:
    known = {p.product_id for p in await list_products(db)}
    ids: set[str] = set()
    out: list[Goal] = []
    for n, g in enumerate(goals, start=1):
        goal_id = g.goal_id.strip() or f"G{n:03d}"
        if goal_id in ids:
            raise AppError("VALIDATION_ERROR", f"Duplicate goal id {goal_id}", 422, "goal_id")
        ids.add(goal_id)
        if missing := [p for p in g.product_ids if p not in known]:
            raise AppError(
                "VALIDATION_ERROR", f"Unknown product(s): {', '.join(missing)}", 422, "product_ids"
            )
        out.append(
            Goal(
                goal_id=goal_id,
                merchant_id=MERCHANT_ID,
                goal_type=g.goal_type.value,
                product_ids=g.product_ids,
                instructions=g.instructions,
            )
        )
    try:
        await db.execute(delete(Goal).where(Goal.merchant_id == MERCHANT_ID))
        db.add_all(out)
        await db.commit()
    except IntegrityError as exc:  # another merchant already owns an id
        await db.rollback()
        raise AppError("VALIDATION_ERROR", "Goal id already in use", 422, "goal_id") from exc
    return out
