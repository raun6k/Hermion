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

            customer.send_json({"type": "select_language", "code": "en-IN"})
            assert customer.receive_json()["type"] == "language_selected"
            assert customer.receive_json()["state"] == "thinking"
            assert customer.receive_json()["state"] == "discovery"
            assert customer.receive_json()["speaker"] == "hermion"
            assert customer.receive_json()["state"] == "idle"
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

        merchant_events = [merchant.receive_json() for _ in range(4)]
        assert merchant_events[1]["type"] == "session_state"
        traces = [merchant_events[0], merchant_events[2], merchant_events[3]]
        assert [t["data"]["speaker"] for t in traces] == ["hermion", "customer", "hermion"]
        assert all(t["type"] == "trace" and t["session_id"] == sid for t in traces)

    assert [s for s, _ in asyncio.run(_messages(sid))] == ["hermion", "customer", "hermion"]


def test_unknown_session_socket_is_refused(client: TestClient) -> None:
    import pytest
    from starlette.websockets import WebSocketDisconnect

    with (
        pytest.raises(WebSocketDisconnect) as exc,
        client.websocket_connect(f"/ws/sessions/{uuid.uuid4()}") as ws,
    ):
        ws.receive_json()
    assert exc.value.code == 4404


def test_language_selection_starts_one_greeting_and_survives_reconnect(client: TestClient) -> None:
    sid = client.post(
        "/sessions", json={"qr_token": "hermion-m001-demo", "device_id": str(uuid.uuid4())}
    ).json()["session_id"]
    with client.websocket_connect(f"/ws/sessions/{sid}") as ws:
        ws.receive_json()
        ws.receive_json()
        ws.send_json({"type": "select_language", "code": "en-IN"})
        assert ws.receive_json() == {"type": "language_selected", "code": "en-IN"}
        assert ws.receive_json() == {"type": "agent_state", "state": "thinking"}
        assert ws.receive_json()["state"] == "discovery"
        greeting = ws.receive_json()
        assert greeting["type"] == "transcript" and greeting["speaker"] == "hermion"
        assert ws.receive_json() == {"type": "agent_state", "state": "idle"}
        ws.send_json({"type": "select_language", "code": "en-IN"})
        assert ws.receive_json() == {"type": "language_selected", "code": "en-IN"}
    with client.websocket_connect(f"/ws/sessions/{sid}") as ws:
        assert ws.receive_json()["state"] == "discovery"
        assert ws.receive_json()["type"] == "agent_state"
        assert ws.receive_json() == greeting
    assert client.get(f"/sessions/{sid}").json()["language"] == "en-IN"
    assert [speaker for speaker, _ in asyncio.run(_messages(sid))] == ["hermion"]


def test_greeting_requires_an_enabled_language(client: TestClient) -> None:
    sid = client.post(
        "/sessions", json={"qr_token": "hermion-m001-demo", "device_id": str(uuid.uuid4())}
    ).json()["session_id"]
    with client.websocket_connect(f"/ws/sessions/{sid}") as ws:
        ws.receive_json()
        ws.receive_json()
        ws.send_json({"type": "text_input", "text": "Hello"})
        assert ws.receive_json()["code"] == "LANGUAGE_REQUIRED"
        ws.send_json({"type": "select_language", "code": "fr-FR"})
        assert ws.receive_json()["code"] == "UNSUPPORTED_LANGUAGE"
    session = client.get(f"/sessions/{sid}").json()
    assert session["state"] == "intro" and session["language"] is None
    assert asyncio.run(_messages(sid)) == []
