"""FastAPI app: wiring only. Run: `uv run uvicorn app.main:app --reload`."""

import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.agent.llm_client import build_llm_client
from app.api import dev, health, rest_customer, rest_merchant, ws_customer, ws_merchant
from app.config import get_settings
from app.db.session import dispose_engine
from app.log import request_id, setup_logging
from app.schemas.common import AppError
from app.services.hub import CustomerHub, Hubs, MerchantHub
from app.speech.translate import build_translator

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings.log_level)
    app.state.settings = settings
    app.state.llm = build_llm_client(settings)
    app.state.merchant_hub = MerchantHub()
    app.state.merchant_hub.translator = build_translator(settings)
    app.state.customer_hub = CustomerHub()
    app.state.hubs = Hubs(app.state.merchant_hub, app.state.customer_hub)
    app.state.turn_locks = {}
    log.info(
        "hermion backend up (llm=%s, fake_llm=%s, fake_speech=%s)",
        settings.llm_model,
        settings.use_fake_llm,
        settings.use_fake_speech,
    )
    yield
    for task in app.state.merchant_hub.translation_tasks:
        task.cancel()
    if app.state.merchant_hub.translation_tasks:
        import asyncio

        await asyncio.gather(*app.state.merchant_hub.translation_tasks, return_exceptions=True)
    await dispose_engine()


def _error(status: int, code: str, message: str, field: str | None = None) -> JSONResponse:
    body = {"code": code, "message": message}
    if field:
        body["field"] = field
    return JSONResponse(status_code=status, content={"error": body})


def create_app() -> FastAPI:
    app = FastAPI(title="Hermion", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def _request_id(request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        request_id.set(rid)
        response = await call_next(request)
        response.headers["x-request-id"] = rid
        return response

    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return _error(exc.status, exc.code, exc.message, exc.field)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return _error(422, "VALIDATION_ERROR", str(exc.errors()[:3]))

    @app.exception_handler(HTTPException)
    async def _http(_: Request, exc: HTTPException) -> JSONResponse:
        return _error(exc.status_code, "HTTP_ERROR", str(exc.detail))

    for router in (
        dev.router,
        health.router,
        rest_customer.router,
        rest_customer.shop_router,
        rest_merchant.router,
        ws_customer.router,
        ws_merchant.router,
    ):
        app.include_router(router)
    return app


app = create_app()
