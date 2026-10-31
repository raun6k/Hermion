"""Merchant WebSocket /ws/merchant: push only (docs/api.md)."""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


@router.websocket("/ws/merchant")
async def merchant_ws(ws: WebSocket, merchant_id: str | None = None) -> None:
    """`?merchant_id=` limits the stream to that shop's sessions (demo shop switch)."""
    await ws.accept()
    hub = ws.app.state.merchant_hub
    hub.add(ws, merchant_id)
    try:
        while True:
            await ws.receive_text()  # ignore input; keeps the socket open
    except WebSocketDisconnect:
        pass
    finally:
        hub.remove(ws)
