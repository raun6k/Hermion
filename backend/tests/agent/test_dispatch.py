"""Tool dispatch against the real services and engine."""

import uuid

from app.agent.tools import ToolContext, dispatch
from app.services import sessions
from tests.helpers import QR, new_hubs, run_db


def _ctx(db, sid):
    return ToolContext(db, new_hubs(), sid)


async def _new(db):
    return (await sessions.create_session(db, QR, f"dev-{uuid.uuid4()}")).session_id


def test_dispatch_walks_the_demo(reseed) -> None:
    async def go(db):
        sid = await _new(db)
        ctx = _ctx(db, sid)
        # intro: no tools yet
        assert await dispatch(ctx, "search_products", {"query": "shirt"}) == {"error": "TOOL_NOT_ALLOWED"}
        await sessions.transition(db, None, sid, sessions.S.discovery)

        found = await dispatch(ctx, "search_products", {"query": "blue shirt M"})
        first = found["products"][0]
        assert first["product_id"] == "SHIRT-BLU-M" and first["listed_price"] == "1000"
        assert not {"target_price", "minimum_price", "unit_cost", "available_stock"} & set(first)

        r = await dispatch(
            ctx, "evaluate_offer", {"items": [{"product_id": "SHIRT-BLU-M"}], "offered_amount": "700"}
        )
        assert (r["decision"], r["price"]) == ("counter", "950") and "threshold" not in r
        assert await dispatch(
            ctx, "evaluate_offer", {"items": [{"product_id": "NOPE"}], "offered_amount": "700"}
        ) == {"error": "UNKNOWN_PRODUCT"}
        assert (await dispatch(ctx, "evaluate_offer", {"items": [], "offered_amount": "700"}))[
            "error"
        ] == "INVALID_ARGUMENTS"
        assert (await dispatch(ctx, "add_to_basket", {"evaluation_id": r["evaluation_id"]})) == {
            "error": "EVALUATION_NOT_ACCEPTED"
        }

        ok = await dispatch(
            ctx, "evaluate_offer", {"items": [{"product_id": "SHIRT-BLU-M"}], "offered_amount": "1000"}
        )
        added = await dispatch(ctx, "add_to_basket", {"evaluation_id": ok["evaluation_id"]})
        assert added == {
            "basket": [
                {
                    "product_id": "SHIRT-BLU-M",
                    "product_name": "Men's cotton shirt, blue",
                    "qty": 1,
                    "line_total": "1000",
                }
            ],
            "total": "1000",
        }
        # injected session_id in arguments changes nothing
        again = await dispatch(
            ctx, "remove_from_basket", {"product_id": "SHIRT-BLU-M", "session_id": str(uuid.uuid4())}
        )
        assert again == {"basket": [], "total": "0"}
        assert await dispatch(ctx, "propose_mandate", {"rules": []}) == {
            "error": "TOOL_NOT_ALLOWED"
        }  # not briefing

    run_db(go)


def test_bundle_tool_and_error_mapping(reseed) -> None:
    async def go(db):
        sid = await _new(db)
        ctx = _ctx(db, sid)
        await sessions.transition(db, None, sid, sessions.S.discovery)
        await dispatch(
            ctx, "evaluate_offer", {"items": [{"product_id": "SHIRT-BLU-M"}], "offered_amount": "1000"}
        )
        b = await dispatch(ctx, "suggest_bundle", {"product_ids": ["SHIRT-BLU-M", "BELT-BRN-32"]})
        assert b["bundle_price"] and {"evaluation_id", "items", "line_prices"} <= set(b)
        oos = await dispatch(
            ctx, "evaluate_offer", {"items": [{"product_id": "SHIRT-WHT-XL"}], "offered_amount": "900"}
        )
        assert oos == {"error": "OUT_OF_STOCK"}
        fixed = await dispatch(
            ctx, "evaluate_offer", {"items": [{"product_id": "SOCKS-3PK"}], "offered_amount": "150"}
        )
        assert (fixed["decision"], fixed["reason_code"], fixed["price"]) == ("reject", "FIXED_PRICE", "250")

    run_db(go)


def test_propose_mandate_in_briefing_does_not_leak_limits(reseed) -> None:
    async def go(db):
        sid = await _new(db)
        s = sessions.S
        for to in (s.discovery, s.negotiating, s.pending_merchant, s.briefing):
            await sessions.transition(db, None, sid, to)
        ctx = _ctx(db, sid)
        res = await dispatch(
            ctx,
            "propose_mandate",
            {"rules": [{"product_id": "BELT-BRN-32", "settle_at": "0", "with_product_id": "SHIRT-BLU-M"}]},
        )
        assert res["limited_product_ids"] == ["BELT-BRN-32"]
        assert "300" not in str(res) and "minimum" not in str(res).lower()
        assert (
            await dispatch(ctx, "propose_mandate", {"rules": [{"product_id": "NOPE", "settle_at": "5"}]})
        ) == {"error": "UNKNOWN_PRODUCT"}
        assert (
            await dispatch(
                ctx, "evaluate_offer", {"items": [{"product_id": "SHIRT-BLU-M"}], "offered_amount": "800"}
            )
        ) == {"error": "TOOL_NOT_ALLOWED"}

    run_db(go)
