import uuid

from fastapi.testclient import TestClient

H2 = {"X-Merchant-Id": "M002"}


def test_same_device_can_resume_independent_shop_sessions(client: TestClient, reseed) -> None:
    device = str(uuid.uuid4())
    qrs = [f"hermion-m00{i}-demo" for i in range(1, 4)]
    sessions = []
    for qr in qrs:
        response = client.post("/sessions", json={"qr_token": qr, "device_id": device})
        assert response.status_code == 201
        sessions.append(response.json()["session_id"])
    assert len(set(sessions)) == 3
    for qr, sid in zip(qrs, sessions, strict=True):
        response = client.post("/sessions", json={"qr_token": qr, "device_id": device})
        assert response.status_code == 200 and response.json()["session_id"] == sid
        visits = client.get("/sessions/visits", params={"qr_token": qr, "device_id": device}).json()
        assert [v["session_id"] for v in visits] == [sid]
    client.post(f"/sessions/{sessions[0]}/exit")
    for sid in sessions[1:]:
        assert client.get(f"/sessions/{sid}").json()["state"] == "intro"


def test_each_shop_has_its_own_catalog_and_sessions(client: TestClient, reseed) -> None:
    ids = {m["merchant_id"] for m in client.get("/merchants").json()}
    assert {"M001", "M002", "M003"} <= ids
    default = {p["product_id"] for p in client.get("/merchant/products").json()}
    electronics = {p["product_id"] for p in client.get("/merchant/products", headers=H2).json()}
    assert "SHIRT-BLU-M" in default and "PHONE-NOVA-128" in electronics and not default & electronics

    sid = client.post(
        "/sessions", json={"qr_token": "hermion-m002-demo", "device_id": str(uuid.uuid4())}
    ).json()["session_id"]
    mine = {s["session_id"] for s in client.get("/merchant/sessions", headers=H2).json()}
    other = {s["session_id"] for s in client.get("/merchant/sessions").json()}
    assert sid in mine and sid not in other
    assert client.get(f"/sessions/{sid}").status_code == 200
    assert client.get("/shop?qr_token=hermion-m002-demo").json()["shop_name"] == "Ameerpet Electronics"


def test_unknown_shop_is_rejected(client: TestClient) -> None:
    assert client.get("/merchant/products", headers={"X-Merchant-Id": "NOPE"}).status_code == 503


def test_merchants_list_has_no_private_fields(client: TestClient) -> None:
    body = client.get("/merchants").text
    for private in ("negotiation_instructions", "escalation", "target_price", "minimum_price", "unit_cost"):
        assert private not in body


def test_session_names_and_guest_numbering(client: TestClient, reseed) -> None:
    qr = "hermion-m003-demo"
    named = client.post(
        "/sessions", json={"qr_token": qr, "device_id": str(uuid.uuid4()), "customer_name": "Asha"}
    ).json()["session_id"]
    guest = client.post("/sessions", json={"qr_token": qr, "device_id": str(uuid.uuid4())}).json()[
        "session_id"
    ]
    rows = {
        s["session_id"]: s for s in client.get("/merchant/sessions", headers={"X-Merchant-Id": "M003"}).json()
    }
    assert rows[named]["display_name"] == "Asha"
    assert rows[guest]["display_name"] == "Guest 1"


def test_merchant_health_is_plain_language(client: TestClient) -> None:
    body = client.get("/merchant/health").json()
    assert {c["key"] for c in body["checks"]} == {"shop_data", "assistant", "voice"}
    assert body["status"] == "ok"
    assert "openrouter" not in str(body).lower() and "sarvam" not in str(body).lower()


def test_shop_page_products_receipt_savings_and_remove(client: TestClient, reseed) -> None:
    from decimal import Decimal

    from app.db.models import SessionState
    from app.engine.types import OfferItem, OfferScope
    from app.services import basket, offers, sessions
    from tests.helpers import new_hubs, run_db

    products = client.get("/shop/products?qr_token=hermion-m002-demo").json()
    electronics = {
        "PHONE",
        "CASE",
        "CHARGER",
        "EARBUDS",
        "MIXER",
        "SPEAKER",
        "POWERBANK",
        "SMARTWATCH",
        "IRON",
        "KETTLE",
    }
    assert products and all(p["product_id"].split("-")[0] in electronics for p in products)
    assert not {"objection_replies", "pairs_with_ids", "upsell_ids"} & set(products[0])
    assert not {"unit_cost", "minimum_price", "target_price"} & set(products[0])

    sid = client.post(
        "/sessions", json={"qr_token": "hermion-m001-demo", "device_id": str(uuid.uuid4())}
    ).json()["session_id"]

    async def go(db):
        hubs = new_hubs()
        await sessions.transition(db, hubs, uuid.UUID(sid), SessionState.discovery)
        item = [OfferItem("SHIRT-BLU-M", 1)]
        r = await offers.evaluate(db, hubs, uuid.UUID(sid), item, Decimal(1000), OfferScope.line, False)
        await basket.add_from_evaluation(db, hubs, uuid.UUID(sid), uuid.UUID(r["evaluation_id"]))

    run_db(go)
    removed = client.delete(f"/sessions/{sid}/basket/SHIRT-BLU-M").json()
    assert removed["lines"] == []
