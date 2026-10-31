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


class MerchantCheck(BaseModel):
    key: Literal["shop_data", "assistant", "voice"]
    state: Literal["ok", "slow", "down"]
    message: str


class MerchantHealth(BaseModel):
    status: Literal["ok", "attention", "down"]
    checks: list[MerchantCheck]


_PLAIN = {
    "db": ("shop_data", "Working", "Shop data is unavailable. Try again in a minute."),
    "openrouter": ("assistant", "Working", "Calls may lag or fail. Try again in a minute."),
    "sarvam": ("voice", "Working", "Voice may be unavailable. Customers can still type."),
}


@router.get("/merchant/health", response_model=MerchantHealth)
async def merchant_health(request: Request) -> MerchantHealth:
    """Plain-language status for the dashboard chip; vendor names stay in logs and `/health`."""
    full = await health(request, Response())
    checks = []
    for name, check in full.checks.items():
        key, ok_message, fix = _PLAIN[name]
        down = check.status == "error"
        if down:
            log.warning("merchant health: %s check failed (%s)", name, check.detail)
        checks.append(
            MerchantCheck(key=key, state="down" if down else "ok", message=fix if down else ok_message)
        )
    bad = sum(c.state == "down" for c in checks)
    return MerchantHealth(
        status="ok" if not bad else "down" if bad == len(checks) else "attention", checks=checks
    )
