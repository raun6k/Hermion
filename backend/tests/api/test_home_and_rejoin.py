"""Customer home page (visits) and rejoining Hermion after sending the basket (docs/api.md)."""

import uuid
from decimal import Decimal

from fastapi.testclient import TestClient

from app.db.models import Message, SessionState
from app.engine.types import OfferItem, OfferScope
from app.services import basket, offers, sessions
from tests.helpers import QR, new_hubs, run_db


def _sent_basket(client: TestClient, device: str) -> str:
    sid = client.post("/sessions", json={"qr_token": QR, "device_id": device}).json()["session_id"]

    async def go(db):
        hubs = new_hubs()
        await sessions.transition(db, hubs, uuid.UUID(sid), SessionState.discovery)
        r = await offers.evaluate(
            db, hubs, uuid.UUID(sid), [OfferItem("SHIRT-BLU-M", 1)], Decimal(1000), OfferScope.line, False
        )
        await basket.add_from_evaluation(db, hubs, uuid.UUID(sid), uuid.UUID(r["evaluation_id"]))

    run_db(go)
    assert client.post(f"/sessions/{sid}/confirm").json()["state"] == "pending_merchant"
    return sid


def test_visits_list_this_devices_baskets_at_the_shop(client: TestClient, reseed) -> None:
    device = str(uuid.uuid4())
    sid = _sent_basket(client, device)
    visits = client.get("/sessions/visits", params={"qr_token": QR, "device_id": device}).json()
    assert [v["session_id"] for v in visits] == [sid]
    assert visits[0]["state"] == "pending_merchant" and visits[0]["basket"]["total"] == "1000.00"
    assert not {"unit_cost", "minimum_price", "contribution"} & set(visits[0]["basket"]["lines"][0])
    other = client.get("/sessions/visits", params={"qr_token": QR, "device_id": str(uuid.uuid4())}).json()
    assert other == []


def test_rejoin_takes_the_basket_back_and_hermion_asks_how_to_help(client: TestClient, reseed) -> None:
    sid = _sent_basket(client, str(uuid.uuid4()))
    assert client.post(f"/sessions/{sid}/rejoin").json()["state"] == "negotiating"
    assert client.get(f"/sessions/{sid}").json()["state"] == "negotiating"

    async def hermion_lines(db):
        from sqlalchemy import select

        rows = await db.scalars(
            select(Message).where(Message.session_id == uuid.UUID(sid), Message.speaker == "hermion")
        )
        return [m.text for m in rows]

    assert len(run_db(hermion_lines)) == 1  # one welcome-back line, nothing else
    # Rejoining again while already negotiating says nothing new; the merchant can no longer accept.
    assert client.post(f"/sessions/{sid}/rejoin").json()["state"] == "negotiating"
    assert len(run_db(hermion_lines)) == 1
    assert client.post(f"/merchant/sessions/{sid}/review", json={"action": "accept"}).status_code == 409
    # The basket is still there and can be sent again.
    assert client.post(f"/sessions/{sid}/confirm").json()["state"] == "pending_merchant"


def test_rejoin_after_the_deal_is_closed_is_refused(client: TestClient, reseed) -> None:
    sid = _sent_basket(client, str(uuid.uuid4()))
    client.post(f"/merchant/sessions/{sid}/review", json={"action": "accept"})
    r = client.post(f"/sessions/{sid}/rejoin")
    assert r.status_code == 409 and r.json()["error"]["code"] == "WRONG_STATE"
