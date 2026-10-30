"""The walking-skeleton slice: customer text -> LLM (fake) -> customer + DB + merchant trace."""

import asyncio
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings
from app.db.models import Message


async def _messages(session_id: str) -> list[tuple[str, str]]:
    engine = create_async_engine(get_settings().database_url)
    async with engine.connect() as conn:
        rows = await conn.execute(
            select(Message.speaker, Message.text)
            .where(Message.session_id == uuid.UUID(session_id))
            .order_by(Message.created_at)
        )
        out = [(r[0], r[1]) for r in rows]
    await engine.dispose()
    return out


def test_customer_text_round_trip(client: TestClient) -> None:
    with client.websocket_connect("/ws/merchant") as merchant:
        sid = client.post(
            "/sessions", json={"qr_token": "hermion-m001-demo", "device_id": str(uuid.uuid4())}
        ).json()["session_id"]
        assert merchant.receive_json()["type"] == "session_created"

        with client.websocket_connect(f"/ws/sessions/{sid}") as customer:
            assert customer.receive_json() == {"type": "state", "state": "intro", "message": None}
            assert customer.receive_json() == {"type": "agent_state", "state": "idle"}

            customer.send_json({"type": "text_input", "text": "Namaskaram"})
            events = [customer.receive_json() for _ in range(4)]
            assert [e["type"] for e in events] == ["transcript", "agent_state", "transcript", "agent_state"]
            assert events[0] == {
                "type": "transcript",
                "speaker": "customer",
                "text": "Namaskaram",
                "final": True,
            }
            assert events[2]["speaker"] == "hermion" and "Namaskaram" in events[2]["text"]

            customer.send_json({"type": "bogus"})
            assert customer.receive_json()["code"] == "INVALID_EVENT"

        traces = [merchant.receive_json() for _ in range(2)]
        assert [t["data"]["speaker"] for t in traces] == ["customer", "hermion"]
        assert all(t["type"] == "trace" and t["session_id"] == sid for t in traces)

    assert [s for s, _ in asyncio.run(_messages(sid))] == ["customer", "hermion"]


def test_unknown_session_socket_is_refused(client: TestClient) -> None:
    import pytest
    from starlette.websockets import WebSocketDisconnect

    with (
        pytest.raises(WebSocketDisconnect) as exc,
        client.websocket_connect(f"/ws/sessions/{uuid.uuid4()}") as ws,
    ):
        ws.receive_json()
    assert exc.value.code == 4404
