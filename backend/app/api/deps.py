"""Shared FastAPI dependencies. Long-lived clients live on app.state (set in main.lifespan)."""

from typing import Annotated

from fastapi import Depends, Request, WebSocket
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


DbDep = Annotated[AsyncSession, Depends(get_db)]
MerchantHubDep = Annotated[MerchantHub, Depends(get_merchant_hub)]
HubsDep = Annotated[Hubs, Depends(get_hubs)]
