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

            customer.send_json({"type": "ui_language", "code": "en-IN"})
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

        messages = {}
        timing = None
        while len(messages) < 3 or timing is None:
            event = merchant.receive_json()
            if event.get("type") == "trace" and event.get("kind") == "message":
                messages[event["data"]["id"]] = event["data"]
            elif event.get("type") == "trace" and event.get("kind") == "timing":
                timing = event["data"]
        assert [m["speaker"] for m in messages.values()] == ["hermion", "customer", "hermion"]
        assert timing["measurements"]["input"] == "text"
        assert timing["measurements"]["speech_end_to_first_audio_ms"] is None
        trace = client.get(f"/merchant/sessions/{sid}").json()
        assert trace["turn_timings"][0]["id"] == timing["id"]

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


def test_ui_language_starts_one_greeting_and_survives_reconnect(client: TestClient) -> None:
    sid = client.post(
        "/sessions", json={"qr_token": "hermion-m001-demo", "device_id": str(uuid.uuid4())}
    ).json()["session_id"]
    with client.websocket_connect(f"/ws/sessions/{sid}") as ws:
        ws.receive_json()
        ws.receive_json()
        ws.send_json({"type": "ui_language", "code": "en-IN"})
        assert ws.receive_json() == {"type": "agent_state", "state": "thinking"}
        assert ws.receive_json()["state"] == "discovery"
        greeting = ws.receive_json()
        assert greeting["type"] == "transcript" and greeting["speaker"] == "hermion"
        assert ws.receive_json() == {"type": "agent_state", "state": "idle"}
        ws.send_json({"type": "ui_language", "code": "en-IN"})  # no second greeting
    with client.websocket_connect(f"/ws/sessions/{sid}") as ws:
        assert ws.receive_json()["state"] == "discovery"
        assert ws.receive_json()["type"] == "agent_state"
        assert ws.receive_json() == greeting
    assert client.get(f"/sessions/{sid}").json()["language"] == "en-IN"
    assert [speaker for speaker, _ in asyncio.run(_messages(sid))] == ["hermion"]


def test_ui_language_must_be_a_shop_language(client: TestClient) -> None:
    sid = client.post(
        "/sessions", json={"qr_token": "hermion-m001-demo", "device_id": str(uuid.uuid4())}
    ).json()["session_id"]
    with client.websocket_connect(f"/ws/sessions/{sid}") as ws:
        ws.receive_json()
        ws.receive_json()
        ws.send_json({"type": "ui_language", "code": "fr-FR"})
        assert ws.receive_json()["code"] == "UNSUPPORTED_LANGUAGE"
    assert asyncio.run(_messages(sid)) == []
