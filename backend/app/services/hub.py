"""In-process WebSocket fan-out. One backend process, so no broker (docs/architecture.md)."""

import logging
from uuid import UUID

from fastapi import WebSocket

from app.schemas.common import Schema

log = logging.getLogger(__name__)


class MerchantHub:
    """Push-only channel to every open merchant console."""

    def __init__(self) -> None:
        self._sockets: set[WebSocket] = set()

    def add(self, ws: WebSocket) -> None:
        self._sockets.add(ws)

    def remove(self, ws: WebSocket) -> None:
        self._sockets.discard(ws)

    async def broadcast(self, event: Schema) -> None:
        payload = event.model_dump(mode="json")
        for ws in list(self._sockets):
            try:
                await ws.send_json(payload)
            except Exception:
                log.warning("dropping dead merchant socket")
                self._sockets.discard(ws)


class CustomerHub:
    """One customer socket per session, so services can push state/basket changes."""

    def __init__(self) -> None:
        self._sockets: dict[UUID, WebSocket] = {}

    def set(self, session_id: UUID, ws: WebSocket) -> None:
        self._sockets[session_id] = ws

    def remove(self, session_id: UUID, ws: WebSocket) -> None:
        if self._sockets.get(session_id) is ws:
            del self._sockets[session_id]

    async def send(self, session_id: UUID, event: Schema) -> None:
        if ws := self._sockets.get(session_id):
            await ws.send_json(event.model_dump(mode="json"))
