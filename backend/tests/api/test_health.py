from fastapi.testclient import TestClient


def test_livez(client: TestClient) -> None:
    assert client.get("/livez").json() == {"status": "ok"}


def test_health_reports_each_dependency(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["checks"]["db"]["status"] == "ok"
    assert body["checks"]["openrouter"]["status"] == "fake"
    assert body["checks"]["sarvam"]["status"] == "fake"


def test_request_id_header(client: TestClient) -> None:
    assert client.get("/livez", headers={"x-request-id": "abc"}).headers["x-request-id"] == "abc"
