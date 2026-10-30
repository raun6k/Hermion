"""Test helpers: run service code against the test DB on its own event loop/engine."""

import asyncio
import os
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.services.hub import CustomerHub, Hubs, MerchantHub

QR = "hermion-m001-demo"


def new_hubs() -> Hubs:
    return Hubs(MerchantHub(), CustomerHub())


async def with_db[T](fn: Callable[[AsyncSession], Awaitable[T]]) -> T:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            return await fn(db)
    finally:
        await engine.dispose()


def run_db[T](fn: Callable[[AsyncSession], Awaitable[T]]) -> T:
    return asyncio.run(with_db(fn))
