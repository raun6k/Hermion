"""Reconnect replays state, basket, last agent_state and the last 20 transcripts (docs/api.md#reconnect)."""

import uuid
from decimal import Decimal as D

from fastapi.testclient import TestClient

from app.engine.types import OfferItem, OfferScope
from app.services import basket, offers
from tests.helpers import QR, new_hubs, run_db


def test_reconnect_replays_everything(client: TestClient, reseed) -> None:
    sid = client.post("/sessions", json={"qr_token": QR, "device_id": f"d-{uuid.uuid4()}"}).json()[
        "session_id"
    ]

    async def add_line(db):
        hubs = new_hubs()
        r = await offers.evaluate(
            db, hubs, uuid.UUID(sid), [OfferItem("SHIRT-BLU-M", 1)], D(1000), OfferScope.line, False
        )
        await basket.add_from_evaluation(db, hubs, uuid.UUID(sid), uuid.UUID(r["evaluation_id"]))

    run_db(add_line)
    with client.websocket_connect(f"/ws/sessions/{sid}") as ws:
        for _ in range(3):  # state, basket, agent_state
            ws.receive_json()
        for n in range(22):  # more than the replay window
            ws.send_json({"type": "text_input", "text": f"msg {n}"})
            for _ in range(4):
                ws.receive_json()
    with client.websocket_connect(f"/ws/sessions/{sid}") as ws:
        first = [ws.receive_json() for _ in range(3)]
        assert [e["type"] for e in first] == ["state", "basket", "agent_state"]
        assert first[0]["state"] == "negotiating"
        assert first[1] == {
            "type": "basket",
            "lines": [
                {
                    "product_id": "SHIRT-BLU-M",
                    "product_name": "Men's cotton shirt, blue",
                    "qty": 1,
                    "line_total": "1000.00",
                    "listed_total": "1000.00",
                }
            ],
            "total": "1000.00",
        }
        assert first[2]["state"] == "idle"
        transcripts = [ws.receive_json() for _ in range(20)]
        assert all(t["type"] == "transcript" for t in transcripts)
        assert transcripts[-1]["speaker"] == "hermion"
        assert transcripts[0]["text"] == "msg 12"  # 44 messages stored, the last 20 replayed
