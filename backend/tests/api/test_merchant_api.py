"""Merchant REST: catalog validation, goals, search, sessions/trace, review and the 409 WRONG_STATE rules."""

import uuid
from decimal import Decimal as D

import pytest
from fastapi.testclient import TestClient

from app.db.models import SessionState
from app.engine.types import OfferItem, OfferScope
from app.services import basket, offers, sessions
from tests.helpers import QR, new_hubs, run_db

NEW = {
    "product_id": "TEST-1",
    "product_name": "Test tee",
    "category": "tees",
    "listed_price": "500.00",
    "target_price": "400.00",
    "minimum_price": "300.00",
    "unit_cost": "200.00",
    "available_stock": 4,
}


def _new_session(client: TestClient) -> str:
    r = client.post("/sessions", json={"qr_token": QR, "device_id": f"dev-{uuid.uuid4()}"})
    return r.json()["session_id"]


def _pending_basket(sid: str, amount: int = 1000, pid: str = "SHIRT-BLU-M") -> None:
    async def go(db):
        hubs = new_hubs()
        r = await offers.evaluate(
            db, hubs, uuid.UUID(sid), [OfferItem(pid, 1)], D(amount), OfferScope.line, False
        )
        await basket.add_from_evaluation(db, hubs, uuid.UUID(sid), uuid.UUID(r["evaluation_id"]))
        await basket.confirm(db, hubs, uuid.UUID(sid))

    run_db(go)


def test_product_crud_and_validation(client: TestClient) -> None:
    assert client.post("/merchant/products", json=NEW).status_code == 201
    assert client.post("/merchant/products", json=NEW).json()["error"]["code"] == "PRODUCT_EXISTS"

    bad = client.patch("/merchant/products/TEST-1", json={"minimum_price": "450"})  # above target
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "VALIDATION_ERROR"
    assert bad.json()["error"]["field"] == "target_price"
    assert client.patch("/merchant/products/TEST-1", json={"listed_price": "250.50"}).status_code == 422
    assert (
        client.patch("/merchant/products/TEST-1", json={"available_stock": -1}).json()["error"]["field"]
        == "available_stock"
    )
    assert client.patch("/merchant/products/TEST-1", json={"minimum_price": "0"}).status_code == 422

    ok = client.patch("/merchant/products/TEST-1", json={"target_price": None, "available_stock": 9})
    assert ok.status_code == 200 and ok.json()["target_price"] is None and ok.json()["available_stock"] == 9
    assert client.patch("/merchant/products/NOPE", json={}).json()["error"]["code"] == "PRODUCT_NOT_FOUND"
    assert client.delete("/merchant/products/TEST-1").status_code == 204
    assert client.delete("/merchant/products/TEST-1").status_code == 404


def test_shop_patch_validates_languages(client: TestClient) -> None:
    assert client.patch("/merchant", json={"languages": ["fr-FR"]}).status_code == 422
    r = client.patch("/merchant", json={"shop_description": "Updated"})
    assert r.json()["shop_description"] == "Updated"
    client.patch(
        "/merchant",
        json={
            "shop_description": "Men's and women's everyday clothing and accessories in Ameerpet, Hyderabad"
        },
    )


def test_goals_replace_and_validate(client: TestClient) -> None:
    before = client.get("/merchant/goals").json()
    assert before[0]["goal_type"] == "clear_stock"
    bad = client.put(
        "/merchant/goals", json=[{"goal_id": "", "goal_type": "clear_stock", "product_ids": ["NOPE"]}]
    )
    assert bad.status_code == 422 and bad.json()["error"]["field"] == "product_ids"
    new = client.put(
        "/merchant/goals", json=[{"goal_id": "", "goal_type": "preserve_stock", "product_ids": []}]
    )
    assert [g["goal_id"] for g in new.json()] == ["G001"]
    assert client.put("/merchant/goals", json=before).json() == before


def test_new_session_in_live_list_and_trace(client: TestClient, reseed) -> None:
    sid = _new_session(client)
    live = {s["session_id"]: s for s in client.get("/merchant/sessions?scope=live").json()}
    assert (
        live[sid]["state"] == "intro" and live[sid]["line_count"] == 0 and live[sid]["basket_total"] is None
    )
    trace = client.get(f"/merchant/sessions/{sid}").json()
    assert trace["messages"] == [] and trace["basket"] is None and trace["mandate"] is None

    client.post(f"/sessions/{sid}/exit")
    assert sid not in {s["session_id"] for s in client.get("/merchant/sessions?scope=live").json()}
    assert sid in {s["session_id"] for s in client.get("/merchant/sessions?scope=past").json()}
    assert client.get(f"/merchant/sessions/{uuid.uuid4()}").status_code == 404


def test_full_trace_shows_thresholds_to_merchant_only(client: TestClient, reseed) -> None:
    sid = _new_session(client)
    _pending_basket(sid)
    trace = client.get(f"/merchant/sessions/{sid}").json()
    assert trace["offers"][0]["threshold"] == "1000.00" or trace["offers"][0]["threshold"] is not None
    assert trace["basket"]["lines"][0]["contribution"] == "370.00"
    confirm = client.post(f"/sessions/{sid}/confirm").json()  # idempotent, customer schema
    assert confirm["state"] == "pending_merchant"
    flat = str(confirm)
    for private in ("threshold", "contribution", "minimum", "unit_cost", "target"):
        assert private not in flat


def test_review_flow_over_http(client: TestClient, reseed) -> None:
    sid = _new_session(client)
    assert client.post(f"/sessions/{sid}/confirm").json()["error"]["code"] == "WRONG_STATE"
    _pending_basket(sid)
    stock = next(p for p in client.get("/merchant/products").json() if p["product_id"] == "SHIRT-BLU-M")[
        "available_stock"
    ]

    assert client.post(
        f"/merchant/sessions/{sid}/review", json={"action": "renegotiate_in_person"}
    ).json() == {"state": "in_person"}
    r = client.put(
        f"/merchant/sessions/{sid}/basket",
        json={"lines": [{"product_id": "SHIRT-BLU-M", "qty": 1, "line_total": "700"}]},
    )
    assert r.status_code == 200 and r.json()["lines"][0]["below_minimum"] is True
    assert client.post(f"/merchant/sessions/{sid}/review", json={"action": "accept"}).json() == {
        "state": "accepted"
    }
    after = next(p for p in client.get("/merchant/products").json() if p["product_id"] == "SHIRT-BLU-M")[
        "available_stock"
    ]
    assert after == stock - 1


def test_illegal_transitions_are_409_wrong_state(client: TestClient, reseed) -> None:
    sid = _new_session(client)
    mid = uuid.uuid4()
    calls = [
        ("post", f"/merchant/sessions/{sid}/review", {"action": a})
        for a in ("accept", "decline", "renegotiate_hermion", "renegotiate_in_person")
    ] + [
        ("post", f"/merchant/sessions/{sid}/mandates/{mid}/confirm", None),
        ("put", f"/merchant/sessions/{sid}/basket", {"lines": []}),
        ("post", f"/sessions/{sid}/confirm", None),
    ]
    for method, path, body in calls:
        r = getattr(client, method)(path, **({"json": body} if body is not None else {}))
        assert r.status_code == 409 and r.json()["error"]["code"] == "WRONG_STATE", (path, r.text)

    client.post(f"/sessions/{sid}/exit")  # terminal: every move is refused
    for a in ("accept", "decline"):
        assert client.post(f"/merchant/sessions/{sid}/review", json={"action": a}).status_code == 409
    assert client.post(f"/sessions/{sid}/exit").json() == {"state": "exited"}  # but exit stays idempotent


def test_empty_basket_confirm_is_400(client: TestClient, reseed) -> None:
    sid = _new_session(client)

    async def go(db):
        await sessions.ensure_negotiating(db, None, await sessions.get_session(db, uuid.UUID(sid)))

    run_db(go)
    r = client.post(f"/sessions/{sid}/confirm")
    assert r.status_code == 400 and r.json()["error"]["code"] == "BASKET_EMPTY"


def test_decline_and_state_pushes(client: TestClient, reseed) -> None:
    with client.websocket_connect("/ws/merchant") as merchant:
        sid = _new_session(client)
        assert merchant.receive_json()["type"] == "session_created"
        with client.websocket_connect(f"/ws/sessions/{sid}") as customer:
            customer.receive_json(), customer.receive_json()  # state, agent_state
            _pending_basket(sid)
            # the app-level hubs live in the TestClient's process, so drive the review over HTTP
            client.post(f"/merchant/sessions/{sid}/review", json={"action": "decline"})
            events = []
            while len(events) < 1:
                events.append(customer.receive_json())
            assert events[0] == {
                "type": "state",
                "state": "declined",
                "message": "Sorry, the shop could not accept this basket. Thank you for visiting!",
            }
    assert run_db(lambda db: sessions.get_session(db, uuid.UUID(sid))).state is SessionState.declined


def test_search_products(client: TestClient) -> None:
    from app.services import catalog

    async def search(db, q):
        return [p.product_id for p in await catalog.search_products(db, q)]

    def run(q):
        return run_db(lambda db: search(db, q))

    assert run("blue shirt M")[0] == "SHIRT-BLU-M"
    assert set(run("kameez")) >= {"SHIRT-BLU-M", "SHIRT-WHT-M"}
    assert run("belt")[0].startswith("BELT-")
    assert run("patta black")[0] == "BELT-BLK-34"
    assert run("socks")[0] == "SOCKS-3PK"
    assert run("zzzzzzzz") == []
    assert len(run("shirt")) <= 5

    from app.services.catalog import to_public

    async def public(db):
        return to_public(next(p for p in await catalog.list_products(db) if p.product_id == "SHIRT-WHT-XL"))

    p = run_db(public)
    assert p.stock_band == "out"
    assert not {"target_price", "minimum_price", "unit_cost", "available_stock"} & set(p.model_dump())


@pytest.mark.parametrize("path", ["/merchant/sessions?scope=bogus"])
def test_bad_scope_is_validation_error(client: TestClient, path: str) -> None:
    assert client.get(path).status_code == 422


def test_private_briefing_proposes_mandate(client: TestClient, reseed) -> None:
    from app.agent.llm_client import FakeLLMClient, LLMResponse, ToolCall

    sid = _new_session(client)
    _pending_basket(sid)
    assert (
        client.post(f"/merchant/sessions/{sid}/review", json={"action": "renegotiate_hermion"}).status_code
        == 200
    )
    client.app.state.llm = FakeLLMClient(
        [
            LLMResponse(
                text=None,
                tool_calls=[
                    ToolCall(
                        "1", "propose_mandate", {"rules": [{"product_id": "SHIRT-BLU-M", "settle_at": "850"}]}
                    )
                ],
            ),
            LLMResponse(text="Please confirm the ₹850 proposal."),
        ]
    )
    response = client.post(f"/merchant/sessions/{sid}/briefing", json={"text": "Offer the shirt for 850"})
    assert response.status_code == 200
    body = response.json()
    assert body["proposed_mandate"]["confirmed"] is False
    assert body["proposed_mandate"]["rules"][0]["settle_at"] == "850.00"
    trace_body = client.get(f"/merchant/sessions/{sid}").json()
    assert [m["channel"] for m in trace_body["messages"]] == ["briefing", "briefing"]
    mandate_id = body["proposed_mandate"]["mandate_id"]
    assert (
        client.post(f"/merchant/sessions/{sid}/mandates/{mandate_id}/confirm").json()["state"]
        == "negotiating"
    )
