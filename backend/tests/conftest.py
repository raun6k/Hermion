"""Test setup: isolated test DB (TEST_DATABASE_URL) migrated + seeded once; fake LLM and speech.

Env is set before any `app` import so Settings pick it up.
"""

import asyncio
import os
from collections.abc import Iterator
from pathlib import Path

from dotenv import dotenv_values

BACKEND = Path(__file__).resolve().parents[1]
_file_env = dotenv_values(BACKEND.parent / ".env")
_test_db = os.environ.get("TEST_DATABASE_URL") or _file_env.get("TEST_DATABASE_URL")
if not _test_db:
    raise RuntimeError("TEST_DATABASE_URL is not set (see .env.example)")
os.environ.update(
    DATABASE_URL=_test_db,
    USE_FAKE_LLM="true",
    USE_FAKE_SPEECH="true",
    OPENROUTER_API_KEY="",
    SARVAM_API_KEY="",
)

import pytest  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from alembic import command  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.seed import seed  # noqa: E402


def alembic_config() -> Config:
    return Config(str(BACKEND / "alembic.ini"))


async def _seed() -> None:
    engine = create_async_engine(_test_db)
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        await seed(db)
    await engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def database() -> None:
    """Fresh schema + seed for the whole test session."""
    get_settings.cache_clear()
    cfg = alembic_config()
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    asyncio.run(_seed())


@pytest.fixture
def client() -> Iterator[TestClient]:
    """App with lifespan (fake LLM, hubs). One per test so the DB engine binds to its loop."""
    from app.main import create_app

    with TestClient(create_app()) as c:
        yield c
