import uuid
from decimal import Decimal

from fastapi.testclient import TestClient

from app.db.models import SessionState
from app.engine.types import OfferItem, OfferScope
from app.services import consent, offers, sessions
from tests.helpers import QR, new_hubs, run_db

SHIRT = [OfferItem("SHIRT-BLU-M", 1)]


def _asked_session(client: TestClient) -> tuple[str, str]:
    """A negotiating session where Hermion has asked the shopkeeper about a 730 offer on a 750 floor."""
    sid = client.post("/sessions", json={"qr_token": QR, "device_id": str(uuid.uuid4())}).json()["session_id"]

    async def go(db):
        from app.services import price_checks

        hubs = new_hubs()
        await sessions.transition(db, hubs, uuid.UUID(sid), SessionState.discovery)
        r = await offers.evaluate(db, hubs, uuid.UUID(sid), SHIRT, Decimal(730), OfferScope.per_unit, True)
        assert r["shopkeeper_check_possible"]
        await price_checks.ask(db, hubs, uuid.UUID(sid), uuid.UUID(r["evaluation_id"]))
        return r["evaluation_id"]

    return sid, run_db(go)


def test_ask_marks_the_session_and_only_once(client: TestClient, reseed) -> None:
    sid, evaluation_id = _asked_session(client)
    row = next(s for s in client.get("/merchant/sessions").json() if s["session_id"] == sid)
    assert row["price_check"]["evaluation_id"] == evaluation_id

    async def again(db):
        from app.schemas.common import AppError
        from app.services import price_checks

        try:
            await price_checks.ask(db, new_hubs(), uuid.UUID(sid), uuid.UUID(evaluation_id))
        except AppError as exc:
            return exc.code

    assert run_db(again) == "ESCALATION_NOT_ALLOWED"


def test_merchant_counter_makes_a_normal_accepted_offer(client: TestClient, reseed) -> None:
    sid, _ = _asked_session(client)
    # the customer offered 730, under the product minimum of 750: "accept as offered" cannot be honoured
    refused = client.post(f"/merchant/sessions/{sid}/price-check", json={"action": "accept"})
    assert refused.status_code == 422 and refused.json()["error"]["code"] == "BELOW_MINIMUM"

    r = client.post(f"/merchant/sessions/{sid}/price-check", json={"action": "counter", "price": "750"})
    assert r.status_code == 200
    body = client.get(f"/merchant/sessions/{sid}").json()
    merchant_offer = body["offers"][-1]
    assert (merchant_offer["decision"], merchant_offer["reason_code"]) == ("accept", "MERCHANT_PRICE")
    assert merchant_offer["price"] == "750.00"
    assert body["session"]["price_check"] is None

    async def stage(db):
        return (await sessions.get_session(db, uuid.UUID(sid))).consent["stage"]

    assert run_db(stage) == "awaiting"  # still needs the customer's own yes
    assert client.post(f"/merchant/sessions/{sid}/price-check", json={"action": "accept"}).status_code == 409


def test_merchant_cannot_go_below_the_minimum(client: TestClient, reseed) -> None:
    sid, _ = _asked_session(client)
    low = client.post(f"/merchant/sessions/{sid}/price-check", json={"action": "counter", "price": "500"})
    assert low.status_code == 422 and low.json()["error"]["code"] == "BELOW_MINIMUM"
    ok = client.post(f"/merchant/sessions/{sid}/price-check", json={"action": "counter", "price": "760"})
    assert ok.status_code == 200
    assert client.get(f"/merchant/sessions/{sid}").json()["offers"][-1]["price"].startswith("760")


def test_decline_clears_the_check_without_an_offer(client: TestClient, reseed) -> None:
    sid, _ = _asked_session(client)
    before = len(client.get(f"/merchant/sessions/{sid}").json()["offers"])
    assert client.post(f"/merchant/sessions/{sid}/price-check", json={"action": "decline"}).status_code == 200
    body = client.get(f"/merchant/sessions/{sid}").json()
    assert len(body["offers"]) == before and body["session"]["price_check"] is None


def test_events_only_reach_the_shops_own_console(client: TestClient, reseed) -> None:
    with (
        client.websocket_connect("/ws/merchant?merchant_id=M002") as other,
        client.websocket_connect("/ws/merchant?merchant_id=M001") as mine,
    ):
        client.post("/sessions", json={"qr_token": QR, "device_id": str(uuid.uuid4())})
        assert mine.receive_json()["type"] == "session_created"
        client.post("/sessions", json={"qr_token": "hermion-m002-demo", "device_id": str(uuid.uuid4())})
        assert other.receive_json()["session"]["state"] == "intro"  # first thing M002's console saw
    assert consent.voice_turn.get() is True
