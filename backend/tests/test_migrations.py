import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
from app.config import get_settings
from tests.conftest import _seed, alembic_config

TABLES = {
    "merchants",
    "products",
    "goals",
    "sessions",
    "messages",
    "offers",
    "basket_lines",
    "mandates",
    "tool_calls",
    "state_changes",
}


async def _tables() -> set[str]:
    engine = create_async_engine(get_settings().database_url)
    async with engine.connect() as conn:
        rows = await conn.execute(text("select tablename from pg_tables where schemaname = 'public'"))
        names = {r[0] for r in rows}
    await engine.dispose()
    return names


def test_down_and_up_round_trip() -> None:
    cfg = alembic_config()
    command.downgrade(cfg, "base")
    assert not TABLES & asyncio.run(_tables())
    command.upgrade(cfg, "head")
    assert asyncio.run(_tables()) >= TABLES
    asyncio.run(_seed())  # restore seed for later tests
