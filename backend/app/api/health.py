"""Liveness (/livez) and dependency health (/health)."""

import asyncio
import logging
from typing import Literal

import httpx
from fastapi import APIRouter, Request, Response
from pydantic import BaseModel
from sqlalchemy import text

from app.config import Settings
from app.db.session import sessionmaker

log = logging.getLogger(__name__)
router = APIRouter(tags=["health"])

Status = Literal["ok", "fake", "error"]


class Check(BaseModel):
    status: Status
    detail: str = ""


class Health(BaseModel):
    status: Literal["ok", "error"]
    checks: dict[str, Check]


async def _db() -> Check:
    try:
        async with sessionmaker()() as db:
            await db.execute(text("SELECT 1"))
        return Check(status="ok")
    except Exception as exc:
        return Check(status="error", detail=type(exc).__name__)


async def _openrouter(s: Settings, client: httpx.AsyncClient) -> Check:
    if s.use_fake_llm:
        return Check(status="fake", detail="USE_FAKE_LLM=true")
    try:
        r = await client.get(
            "https://openrouter.ai/api/v1/key", headers={"Authorization": f"Bearer {s.openrouter_api_key}"}
        )
        return (
            Check(status="ok", detail=s.llm_model)
            if r.status_code == 200
            else Check(status="error", detail=f"HTTP {r.status_code}")
        )
    except httpx.HTTPError as exc:
        return Check(status="error", detail=type(exc).__name__)


async def _sarvam(s: Settings, client: httpx.AsyncClient) -> Check:
    """Reachability only: Sarvam has no free key-check endpoint. `make smoke` verifies the key."""
    if s.use_fake_speech:
        return Check(status="fake", detail="USE_FAKE_SPEECH=true")
    try:
        r = await client.get("https://api.sarvam.ai/", headers={"api-subscription-key": s.sarvam_api_key})
        return (
            Check(status="ok", detail="reachable")
            if r.status_code < 500
            else Check(status="error", detail=f"HTTP {r.status_code}")
        )
    except httpx.HTTPError as exc:
        return Check(status="error", detail=type(exc).__name__)


@router.get("/livez")
async def livez() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health", response_model=Health)
async def health(request: Request, response: Response) -> Health:
    settings: Settings = request.app.state.settings
    async with httpx.AsyncClient(timeout=5) as client:
        db, orr, sv = await asyncio.gather(_db(), _openrouter(settings, client), _sarvam(settings, client))
    checks = {"db": db, "openrouter": orr, "sarvam": sv}
    ok = all(c.status != "error" for c in checks.values())
    response.status_code = 200 if ok else 503
    return Health(status="ok" if ok else "error", checks=checks)
