"""Phase 1 service behaviour: public product fields, headroom/read in results, addons, escalation."""

import uuid
from decimal import Decimal

from app.db.models import Merchant, Product, SessionState
from app.engine.types import OfferItem, OfferScope
from app.services import basket, catalog, offers, sessions
from tests.helpers import QR, new_hubs, with_db

SHIRT = [OfferItem("SHIRT-BLU-M", 1)]


async def _negotiating(db, hubs):
    session = await sessions.create_session(db, QR, str(uuid.uuid4()))
    await sessions.transition(db, hubs, session.session_id, SessionState.discovery)
    return session.session_id


async def test_search_results_carry_only_provided_persuasion_fields() -> None:
    async def exercise(db):
        found = await catalog.search_products(db, "blue shirt M")
        shirt = next(p for p in found if p.product_id == "SHIRT-BLU-M")
        assert shirt.pitch and shirt.selling_points and shirt.specs and shirt.best_for
        dumped = shirt.model_dump()
        assert shirt.objection_replies  # Hermion gets the shop's answers to objections
        assert not {"pairs_with_ids", "upsell_ids", "unit_cost", "minimum_price"} & set(dumped)
        assert "objection_replies" not in catalog.to_public(await db.get(Product, "SHIRT-BLU-M")).model_dump()

    await with_db(exercise)


async def test_result_has_headroom_and_read_but_no_floor_numbers() -> None:
    async def exercise(db):
        hubs = new_hubs()
        sid = await _negotiating(db, hubs)
        r = await offers.evaluate(
            db, hubs, sid, SHIRT, Decimal(700), OfferScope.per_unit, False, Decimal(900)
        )
        assert r["decision"] == "counter" and r["price"] == "900"
        assert r["headroom"] in {"high", "medium", "low", "none"}
        assert r["customer_read"] in {"lowballer", "value_seeker", "ready_to_buy", "browsing"}
        assert not {"threshold", "floor", "target", "minimum_price"} & set(r)

    await with_db(exercise)


async def test_below_floor_proposal_is_replaced_and_logged() -> None:
    async def exercise(db):
        hubs = new_hubs()
        sid = await _negotiating(db, hubs)
        r = await offers.evaluate(
            db, hubs, sid, SHIRT, Decimal(600), OfferScope.per_unit, False, Decimal(300)
        )
        assert r["reason_code"] == "PROPOSAL_BELOW_FLOOR"
        assert Decimal(r["price"]) > 750

    await with_db(exercise)


async def test_upsell_before_basket_and_cross_sell_after(reseed) -> None:
    async def exercise(db):
        hubs = new_hubs()
        sid = await _negotiating(db, hubs)
        before = await catalog.suggest_addons(db, sid, ["SHIRT-BLU-M"])
        assert before and {a["reason_tag"] for a in before} == {"upgrade"}
        assert all(a["pitch"] and a["for_product_id"] == "SHIRT-BLU-M" for a in before)
        ok = await offers.evaluate(db, hubs, sid, SHIRT, Decimal(1000), OfferScope.line, False)
        await basket.add_from_evaluation(db, hubs, sid, uuid.UUID(ok["evaluation_id"]))
        after = await catalog.suggest_addons(db, sid, ["SHIRT-BLU-M"])
        assert 0 < len(after) <= 2 and "pairs_with" in {a["reason_tag"] for a in after}
        assert not {a["product_id"] for a in after} & {"SHIRT-BLU-M"}
        merchant = await db.get(Merchant, "M001")
        merchant.upsell_enabled = False
        await db.commit()
        still_suggested = await catalog.suggest_addons(db, sid, ["SHIRT-BLU-M"])
        assert still_suggested  # legacy database flag no longer controls suggestions

    await with_db(exercise)


async def test_serious_below_floor_offer_flags_a_shopkeeper_check_but_a_lowball_does_not(reseed) -> None:
    async def exercise(db):
        hubs = new_hubs()
        sid = await _negotiating(db, hubs)
        r = await offers.evaluate(db, hubs, sid, SHIRT, Decimal(650), OfferScope.per_unit, False)
        assert r.get("shopkeeper_check_possible") is True  # 65% of listed, well below floor
        low = await _negotiating(db, hubs)
        r = await offers.evaluate(db, hubs, low, SHIRT, Decimal(400), OfferScope.per_unit, False)
        assert "shopkeeper_check_possible" not in r  # lowballer

    await with_db(exercise)


async def test_rare_mode_only_flags_a_close_high_intent_offer(reseed) -> None:
    async def exercise(db):
        hubs = new_hubs()
        (await db.get(Merchant, "M001")).escalation = "rare"
        await db.commit()
        sid = await _negotiating(db, hubs)
        r = await offers.evaluate(db, hubs, sid, SHIRT, Decimal(730), OfferScope.per_unit, True)
        assert r.get("shopkeeper_check_possible") is True
        far = await offers.evaluate(db, hubs, sid, SHIRT, Decimal(400), OfferScope.per_unit, True)
        assert "shopkeeper_check_possible" not in far

    await with_db(exercise)
