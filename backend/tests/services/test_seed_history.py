"""History is replayed through the real engine; stats are computed from it and it can be purged."""

from sqlalchemy import func, select

from app.db.models import Product, Session
from app.seed_history import clear, generate
from app.services import stats
from tests.helpers import with_db


async def test_history_feeds_real_stats_and_clears(reseed) -> None:
    async def exercise(db):
        stock = {p.product_id: p.available_stock for p in await db.scalars(select(Product))}
        made = await generate(db, days=3)
        assert made > 0
        assert (
            await db.scalar(select(func.count()).select_from(Session).where(Session.source == "seed")) == made
        )
        # engine bounds hold for every replayed accepted line
        data = await stats.merchant_stats(db, "M001", days=7)
        assert data.funnel.scanned >= data.funnel.started >= data.funnel.offered
        assert data.funnel.accepted <= data.funnel.confirmed <= data.funnel.in_basket
        assert data.revenue_won >= 0 and data.per_day
        assert {p.product_id: p.available_stock for p in await db.scalars(select(Product))} == stock
        assert (await stats.merchant_stats(db, "M002")).sessions > 0
        await clear(db)
        assert await stats.merchant_stats(db, "M001") is not None
        assert await db.scalar(select(func.count()).select_from(Session).where(Session.source == "seed")) == 0

    await with_db(exercise)
