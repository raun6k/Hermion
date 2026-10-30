import uuid

from fastapi.testclient import TestClient

QR = "hermion-m001-demo"


def test_merchant_profile_and_products(client: TestClient) -> None:
    assert client.get("/merchant").json()["shop_name"] == "Lakshmi Fashions"
    products = client.get("/merchant/products").json()
    assert len(products) == 12
    shirt = next(p for p in products if p["product_id"] == "SHIRT-BLU-M")
    assert shirt["listed_price"] == "1000.00"  # money is a string on the wire
    assert shirt["minimum_price"] == "750.00"


def test_session_lifecycle(client: TestClient) -> None:
    device = f"dev-{uuid.uuid4()}"
    r = client.post("/sessions", json={"qr_token": QR, "device_id": device})
    assert r.status_code == 201
    sid = r.json()["session_id"]

    again = client.post("/sessions", json={"qr_token": QR, "device_id": device})
    assert again.status_code == 409
    assert again.json() == {
        "error": {"code": "SESSION_ACTIVE", "message": "Exit your current session to scan again"}
    }

    assert client.post(f"/sessions/{sid}/exit").json() == {"state": "exited"}
    assert client.post(f"/sessions/{sid}/exit").json() == {"state": "exited"}  # idempotent
    assert client.post("/sessions", json={"qr_token": QR, "device_id": device}).status_code == 201


def test_unknown_qr(client: TestClient) -> None:
    r = client.post("/sessions", json={"qr_token": "nope", "device_id": "d"})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "UNKNOWN_QR"


def test_validation_uses_error_envelope(client: TestClient) -> None:
    r = client.post("/sessions", json={"qr_token": QR})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_unbuilt_routes_return_501(client: TestClient) -> None:
    sid = uuid.uuid4()
    for method, path in [
        ("get", "/merchant/stats"),
        ("get", "/merchant/sessions"),
        ("post", f"/sessions/{sid}/confirm"),
        ("get", f"/merchant/sessions/{sid}"),
    ]:
        r = getattr(client, method)(path)
        assert r.status_code == 501, path
        assert r.json()["error"]["code"] == "NOT_IMPLEMENTED"


def test_tts_test_clip_is_wav(client: TestClient) -> None:
    r = client.get("/dev/tts-test?lang=hi-IN")
    assert r.status_code == 200
    assert r.content[:4] == b"RIFF"
