"""Shared FastAPI dependencies. Long-lived clients live on app.state (set in main.lifespan)."""

from typing import Annotated

from fastapi import Depends, Header, Request, WebSocket
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.llm_client import LLMClient
from app.db.session import get_db
from app.services.hub import CustomerHub, Hubs, MerchantHub


def _state(conn: Request | WebSocket):
    return conn.app.state


def get_llm(request: Request) -> LLMClient:
    return _state(request).llm


def get_merchant_hub(request: Request) -> MerchantHub:
    return _state(request).merchant_hub


def get_customer_hub(request: Request) -> CustomerHub:
    return _state(request).customer_hub


def get_hubs(request: Request) -> Hubs:
    return _state(request).hubs


async def get_merchant_id(
    db: Annotated[AsyncSession, Depends(get_db)], x_merchant_id: str | None = Header(None)
) -> str:
    """Demo-only shop switch: the dashboard sends the chosen shop; no header means the default shop."""
    from app.services import catalog

    merchant_id = x_merchant_id or catalog.DEFAULT_MERCHANT_ID
    await catalog.get_merchant(db, merchant_id)  # 503 MERCHANT_NOT_SEEDED if unknown
    return merchant_id


DbDep = Annotated[AsyncSession, Depends(get_db)]
MerchantIdDep = Annotated[str, Depends(get_merchant_id)]
MerchantHubDep = Annotated[MerchantHub, Depends(get_merchant_hub)]
HubsDep = Annotated[Hubs, Depends(get_hubs)]
