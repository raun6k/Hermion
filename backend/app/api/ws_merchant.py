"""Merchant WebSocket /ws/merchant: push only (docs/api.md)."""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


@router.websocket("/ws/merchant")
async def merchant_ws(ws: WebSocket) -> None:
    await ws.accept()
    hub = ws.app.state.merchant_hub
    hub.add(ws)
    try:
        while True:
            await ws.receive_text()  # ignore input; keeps the socket open
    except WebSocketDisconnect:
        pass
    finally:
        hub.remove(ws)
