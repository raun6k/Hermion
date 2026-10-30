"""Services on the real engine and DB: offers, basket, confirm, review, mandates, in-person edits."""

import uuid
from decimal import Decimal as D

import pytest
from sqlalchemy import select

from app.db.models import Offer, Product, SessionState
from app.engine.types import OfferItem, OfferScope
from app.schemas.common import AppError
from app.schemas.merchant import BasketEditLine, ReviewAction
from app.services import basket, mandates, offers, sessions, views
from tests.helpers import QR, new_hubs, run_db

SHIRT, BELT, SOCKS = "SHIRT-BLU-M", "BELT-BRN-32", "SOCKS-3PK"


async def _start(db, hubs):
    s = await sessions.create_session(db, QR, f"dev-{uuid.uuid4()}")
    return s.session_id


async def _offer(db, hubs, sid, pid, amount, *, qty=1, scope=OfferScope.per_unit, buy_now=False):
    return await offers.evaluate(db, hubs, sid, [OfferItem(pid, qty)], D(amount), scope, buy_now)


def test_worked_example_and_basket(reseed) -> None:
    async def go(db):
        hubs = new_hubs()
        sid = await _start(db, hubs)
        first = await _offer(db, hubs, sid, SHIRT, 700)
        assert (first["decision"], first["price"], first["round"]) == ("counter", "950", 1)
        assert "threshold" not in first and "minimum" not in str(first).lower()
        assert (await sessions.get_session(db, sid)).state is SessionState.negotiating
        assert (await _offer(db, hubs, sid, SHIRT, 750))["price"] == "900"
        done = await _offer(db, hubs, sid, SHIRT, 800, buy_now=True)
        assert (done["decision"], done["price"]) == ("accept", "800")

        public = await basket.add_from_evaluation(db, hubs, sid, uuid.UUID(done["evaluation_id"]))
        assert [(ln.product_id, ln.line_total) for ln in public.lines] == [(SHIRT, D(800))]
        again = await basket.add_from_evaluation(
            db, hubs, sid, uuid.UUID(done["evaluation_id"])
        )  # idempotent
        assert again.total == D(800)

        offers_rows = list(await db.scalars(select(Offer).where(Offer.session_id == sid)))
        assert [o.round for o in offers_rows] == [1, 2, 3]
        assert all(o.threshold is not None for o in offers_rows)  # merchant log keeps the threshold

    run_db(go)


def test_basket_takes_only_accepted_and_one_line_per_product(reseed) -> None:
    async def go(db):
        hubs = new_hubs()
        sid = await _start(db, hubs)
        counter = await _offer(db, hubs, sid, SHIRT, 700)
        with pytest.raises(AppError) as exc:
            await basket.add_from_evaluation(db, hubs, sid, uuid.UUID(counter["evaluation_id"]))
        assert exc.value.code == "EVALUATION_NOT_ACCEPTED"
        with pytest.raises(AppError) as exc:
            await basket.add_from_evaluation(db, hubs, sid, uuid.uuid4())
        assert exc.value.code == "EVALUATION_NOT_FOUND"

        a = await _offer(db, hubs, sid, SHIRT, 950)
        await basket.add_from_evaluation(db, hubs, sid, uuid.UUID(a["evaluation_id"]))
        b = await _offer(db, hubs, sid, SHIRT, 900)
        public = await basket.add_from_evaluation(db, hubs, sid, uuid.UUID(b["evaluation_id"]))
        assert [ln.line_total for ln in public.lines] == [D(900)]  # replaced, not stacked

        removed = await basket.remove(db, hubs, sid, SHIRT)
        assert removed.lines == []

    run_db(go)


def test_errors_and_fixed_price_through_services(reseed) -> None:
    async def go(db):
        hubs = new_hubs()
        sid = await _start(db, hubs)
        assert (await _offer(db, hubs, sid, "NOPE", 100))["reason_code"] == "UNKNOWN_PRODUCT"
        assert (await _offer(db, hubs, sid, "SHIRT-WHT-XL", 500))["reason_code"] == "OUT_OF_STOCK"
        assert (await _offer(db, hubs, sid, "SHIRT-BLU-L", 2000, qty=3, scope=OfferScope.line))[
            "reason_code"
        ] == "INSUFFICIENT_STOCK"
        # error evaluations are logged but are not negotiation rounds, and do not leave `discovery`
        assert (await sessions.get_session(db, sid)).state is SessionState.intro
        socks = await _offer(db, hubs, sid, SOCKS, 150)
        assert (socks["reason_code"], socks["price"]) == ("FIXED_PRICE", "250")
        ok = await _offer(db, hubs, sid, SOCKS, 250)
        assert ok["decision"] == "accept"

    run_db(go)


def test_basket_scope_and_clear_stock_goal(reseed) -> None:
    async def go(db):
        hubs = new_hubs()
        sid = await _start(db, hubs)
        items = [OfferItem(SHIRT, 1), OfferItem(BELT, 1)]
        low = await offers.evaluate(db, hubs, sid, items, D(1100), OfferScope.basket, False)
        assert (low["decision"], low["price"]) == ("counter", "1350")
        ok = await offers.evaluate(db, hubs, sid, items, D(1400), OfferScope.basket, False)
        assert ok["decision"] == "accept"
        public = await basket.add_from_evaluation(db, hubs, sid, uuid.UUID(ok["evaluation_id"]))
        assert sum(ln.line_total for ln in public.lines) == D(1400)
        assert len(public.lines) == 2

        # clear_stock goal on the maroon kurtas adds a round of concession
        s2 = await _start(db, hubs)
        kurta = await _offer(db, hubs, s2, "KURTA-MRN-M", 100)
        assert kurta["price"] == "1280"  # e = 1 + clear_stock = 2: T = 1400 - 250 * 2 / 4 = 1275

    run_db(go)


def test_confirm_review_accept_decrements_stock(reseed) -> None:
    async def go(db):
        hubs = new_hubs()
        sid = await _start(db, hubs)
        with pytest.raises(AppError) as exc:
            await basket.confirm(db, hubs, sid)
        assert exc.value.code == "WRONG_STATE"  # still in intro

        r = await _offer(db, hubs, sid, SHIRT, 1000)
        await basket.add_from_evaluation(db, hubs, sid, uuid.UUID(r["evaluation_id"]))
        session, public = await basket.confirm(db, hubs, sid)
        assert session.state is SessionState.pending_merchant and public.total == D(1000)
        session, _ = await basket.confirm(db, hubs, sid)  # idempotent
        assert session.state is SessionState.pending_merchant

        mb = await views.merchant_basket(db, sid)
        assert mb.contribution == D(370) and mb.lines[0].listed_price == D(1000)

        done = await basket.review(db, hubs, sid, ReviewAction.accept)
        assert done.state is SessionState.accepted
        stock = (await db.get(Product, SHIRT)).available_stock
        assert stock == 14
        with pytest.raises(AppError) as exc:
            await basket.review(db, hubs, sid, ReviewAction.accept)
        assert exc.value.code == "WRONG_STATE"

    run_db(go)


def test_confirm_drops_line_that_became_invalid(reseed) -> None:
    async def go(db):
        hubs = new_hubs()
        sid = await _start(db, hubs)
        r = await _offer(db, hubs, sid, "SHIRT-BLU-L", 1000)
        await basket.add_from_evaluation(db, hubs, sid, uuid.UUID(r["evaluation_id"]))
        (await db.get(Product, "SHIRT-BLU-L")).available_stock = 0
        await db.commit()
        with pytest.raises(AppError) as exc:
            await basket.confirm(db, hubs, sid)
        assert exc.value.code == "LINE_INVALID" and exc.value.status == 409
        assert (await views.public_basket(db, sid)).lines == []
        assert (await sessions.get_session(db, sid)).state is SessionState.negotiating

    run_db(go)


def test_mandate_flow_and_bundle_price(reseed) -> None:
    async def go(db):
        hubs = new_hubs()
        sid = await _start(db, hubs)
        for amount in (700, 750):
            await _offer(db, hubs, sid, SHIRT, amount)
        r = await _offer(db, hubs, sid, SHIRT, 800, buy_now=True)
        await basket.add_from_evaluation(db, hubs, sid, uuid.UUID(r["evaluation_id"]))
        await basket.confirm(db, hubs, sid)
        await basket.review(db, hubs, sid, ReviewAction.renegotiate_hermion)

        args = mandates.MandateArgs(
            rules=[
                mandates.RuleArgs(product_id=SHIRT, settle_at=D(850), with_product_id=BELT),
                mandates.RuleArgs(product_id=BELT, settle_at=D(0), with_product_id=SHIRT),  # "free belt"
            ]
        )
        mandate, proposal = await mandates.propose(db, hubs, sid, args)
        assert proposal.limited_product_ids == [BELT]  # the engine refuses a free belt
        assert {r.product_id: r.settle_at for r in proposal.rules} == {SHIRT: D(850), BELT: D(300)}
        assert "₹0" in proposal.readable and "300" not in proposal.readable  # LLM-safe text: no minimum

        assert await mandates.confirm(db, hubs, sid, mandate.id) is SessionState.negotiating
        bundle = await offers.suggest_bundle(db, hubs, sid, [SHIRT, BELT])
        assert bundle is not None and bundle["bundle_price"] == "1150"
        await basket.add_from_evaluation(db, hubs, sid, uuid.UUID(bundle["evaluation_id"]))
        public = await views.public_basket(db, sid)
        assert {ln.product_id: ln.line_total for ln in public.lines} == {SHIRT: D(850), BELT: D(300)}
        assert (
            await db.scalar(select(Offer.mandate_id).where(Offer.id == uuid.UUID(bundle["evaluation_id"])))
        ) == mandate.id

        # bundle quotes are not negotiation rounds
        ctx = await offers.build_context(db, await sessions.get_session(db, sid))
        assert ctx.rounds[SHIRT] == 3 and BELT not in ctx.rounds

    run_db(go)


def test_in_person_edit_flags_below_minimum(reseed) -> None:
    async def go(db):
        hubs = new_hubs()
        sid = await _start(db, hubs)
        r = await _offer(db, hubs, sid, SHIRT, 1000)
        await basket.add_from_evaluation(db, hubs, sid, uuid.UUID(r["evaluation_id"]))
        await basket.confirm(db, hubs, sid)
        with pytest.raises(AppError) as exc:  # not in person yet
            await basket.edit_in_person(
                db, hubs, sid, [BasketEditLine(product_id=SHIRT, qty=1, line_total=D(700))]
            )
        assert exc.value.code == "WRONG_STATE"
        await basket.review(db, hubs, sid, ReviewAction.renegotiate_in_person)
        mb = await basket.edit_in_person(
            db,
            hubs,
            sid,
            [
                BasketEditLine(product_id=SHIRT, qty=1, line_total=D(700)),
                BasketEditLine(product_id=BELT, qty=2, line_total=D(900)),
            ],
        )
        flags = {ln.product_id: ln.below_minimum for ln in mb.lines}
        assert flags == {SHIRT: True, BELT: False} and mb.total == D(1600)
        assert (await basket.review(db, hubs, sid, ReviewAction.accept)).state is SessionState.accepted

    run_db(go)


def test_transition_table() -> None:
    S = SessionState
    legal = {
        (S.intro, S.discovery),
        (S.discovery, S.negotiating),
        (S.negotiating, S.pending_merchant),
        (S.pending_merchant, S.accepted),
        (S.pending_merchant, S.declined),
        (S.pending_merchant, S.briefing),
        (S.pending_merchant, S.in_person),
        (S.briefing, S.negotiating),
        (S.in_person, S.accepted),
        (S.in_person, S.declined),
    }
    terminal = {S.accepted, S.declined, S.exited}
    for a in S:
        for b in S:
            expected = (a, b) in legal or (a not in terminal and b is S.exited)
            assert sessions.can_transition(a, b) is expected, (a, b)
