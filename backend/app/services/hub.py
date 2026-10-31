"""In-process WebSocket fan-out. One backend process, so no broker (docs/architecture.md)."""

import asyncio
import logging
from dataclasses import dataclass
from uuid import UUID

from fastapi import WebSocket

from app.schemas.common import Schema

log = logging.getLogger(__name__)


class MerchantHub:
    """Push-only channel to every open merchant console."""

    def __init__(self) -> None:
        self._sockets: set[WebSocket] = set()
        self._owner: dict[WebSocket, str | None] = {}  # which shop's console this socket is
        self._session_owner: dict[UUID, str] = {}
        self.translator = None
        self.translation_tasks: set[asyncio.Task] = set()

    def add(self, ws: WebSocket, merchant_id: str | None = None) -> None:
        self._sockets.add(ws)
        self._owner[ws] = merchant_id

    def remove(self, ws: WebSocket) -> None:
        self._sockets.discard(ws)
        self._owner.pop(ws, None)

    async def _shop_of(self, event: Schema) -> str | None:
        """The shop an event belongs to, found through its session (cached)."""
        sid = getattr(event, "session_id", None) or getattr(
            getattr(event, "session", None), "session_id", None
        )
        if sid is None:
            return None
        if sid not in self._session_owner:
            from app.db.models import Session
            from app.db.session import sessionmaker

            async with sessionmaker()() as db:
                row = await db.get(Session, sid)
            if row is None:
                return None
            self._session_owner[sid] = row.merchant_id
        return self._session_owner[sid]

    async def broadcast(self, event: Schema) -> None:
        payload = event.model_dump(mode="json")
        shop = await self._shop_of(event) if any(self._owner.values()) else None
        for ws in list(self._sockets):
            if shop is not None and self._owner.get(ws) not in (None, shop):
                continue
            try:
                await ws.send_json(payload)
            except Exception:
                log.warning("dropping dead merchant socket")
                self._sockets.discard(ws)


class CustomerHub:
    """One customer socket per session, so services can push state/basket changes."""

    def __init__(self) -> None:
        self._sockets: dict[UUID, WebSocket] = {}
        self.speech_callbacks = {}
        self._agent_state: dict[UUID, str] = {}  # last mascot state, replayed on reconnect

    def set(self, session_id: UUID, ws: WebSocket) -> None:
        self._sockets[session_id] = ws

    def last_agent_state(self, session_id: UUID) -> str:
        return self._agent_state.get(session_id, "idle")

    def remove(self, session_id: UUID, ws: WebSocket) -> None:
        if self._sockets.get(session_id) is ws:
            del self._sockets[session_id]

    async def send(self, session_id: UUID, event: Schema) -> None:
        payload = event.model_dump(mode="json")
        if payload.get("type") == "agent_state":
            self._agent_state[session_id] = payload["state"]
        if ws := self._sockets.get(session_id):
            try:
                await ws.send_json(payload)
            except Exception:
                log.warning("dropping dead customer socket")
                self.remove(session_id, ws)


@dataclass(frozen=True)
class Hubs:
    merchant: MerchantHub
    customer: CustomerHub
