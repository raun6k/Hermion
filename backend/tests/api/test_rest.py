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
    for method, path, body in [
        ("get", "/merchant/stats", None),  # Stage 3
    ]:
        r = getattr(client, method)(path, **({"json": body} if body else {}))
        assert r.status_code == 501, path
        assert r.json()["error"]["code"] == "NOT_IMPLEMENTED"


def test_tts_test_clip_any_supported_language(client: TestClient) -> None:
    for lang in ("hi-IN", "kn-IN", "od-IN"):
        r = client.get(f"/dev/tts-test?lang={lang}")
        assert r.status_code == 200, lang
        assert r.content[:4] == b"RIFF"


def test_tts_test_clip_rejects_unsupported_language(client: TestClient) -> None:
    r = client.get("/dev/tts-test?lang=fr-FR")
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "UNSUPPORTED_LANGUAGE"


def test_dev_tts_stream_and_stt_socket(client: TestClient) -> None:
    r = client.get("/dev/tts-stream?lang=te-IN&text=Namaskaram. Hello.")
    assert r.status_code == 200 and r.headers["content-type"].startswith("audio/L16;rate=24000")
    assert len(r.content) == 2 * 3 * 2400 * 2  # two sentences x three 100 ms chunks, 16-bit
    assert client.get("/dev/tts-stream?lang=fr-FR").status_code == 400

    with client.websocket_connect("/dev/stt?lang=auto") as ws:
        assert ws.receive_json() == {"type": "ready"}
        for _ in range(10):
            ws.send_bytes(b"\x01\x00" * 1600)
        types = [ws.receive_json()["type"] for _ in range(4)]
        assert types == ["speech_start", "partial", "speech_end", "final"]


def test_customer_session_view_exposes_only_public_facts(client: TestClient) -> None:
    sid = client.post("/sessions", json={"qr_token": QR, "device_id": f"d-{uuid.uuid4()}"}).json()[
        "session_id"
    ]
    r = client.get(f"/sessions/{sid}")
    assert r.status_code == 200
    assert r.json() == {
        "session_id": sid,
        "state": "intro",
        "language": None,
        "languages": ["hi-IN", "te-IN", "kn-IN", "en-IN"],
    }
    assert client.get(f"/sessions/{uuid.uuid4()}").json()["error"]["code"] == "SESSION_NOT_FOUND"
    client.post(f"/sessions/{sid}/exit")
