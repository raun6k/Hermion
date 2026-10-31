import asyncio
import uuid
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models import BasketLine, Message, Session, SessionState, TurnTiming
from app.services import stats, trace
from app.services.hub import MerchantHub
from app.speech.translate import FakeTranslator
from tests.helpers import QR, run_db


def test_response_average_distinguishes_missing_data_and_measured_turns(client: TestClient, reseed) -> None:
    sid = uuid.UUID(
        client.post("/sessions", json={"qr_token": QR, "device_id": str(uuid.uuid4())}).json()["session_id"]
    )

    async def exercise(db):
        shop_sessions = select(Session.session_id).where(Session.merchant_id.in_(["M001", "M002"]))
        await db.execute(delete(TurnTiming).where(TurnTiming.session_id.in_(shop_sessions)))
        await db.commit()
        assert (await stats.merchant_stats(db, "M001")).avg_response_ms is None
        message = Message(session_id=sid, channel="customer", speaker="customer", text="Hello")
        db.add(message)
        await db.flush()
        db.add_all(
            [
                TurnTiming(session_id=sid, message_id=message.id, measurements={"agent_ms": 1200}),
                TurnTiming(session_id=sid, message_id=message.id, measurements={"agent_ms": 2400}),
            ]
        )
        await db.commit()
        assert (await stats.merchant_stats(db, "M001")).avg_response_ms == 1800
        assert (await stats.merchant_stats(db, "M002")).avg_response_ms is None

    run_db(exercise)


def test_stats_accepted_lines_and_current_catalog_values(client: TestClient, reseed) -> None:
    sid = uuid.UUID(
        client.post("/sessions", json={"qr_token": QR, "device_id": str(uuid.uuid4())}).json()["session_id"]
    )

    async def setup(db):
        session = await db.get(Session, sid)
        session.state = SessionState.accepted
        db.add(BasketLine(session_id=sid, product_id="SHIRT-BLU-M", qty=2, line_total=Decimal("1800")))
        await db.commit()
        return await stats.merchant_stats(db, "M001")

    result = run_db(setup)
    assert result.deals == 1
    assert result.avg_discount_pct == Decimal("10.00")
    assert result.total_contribution == Decimal("540.00")
    outcomes = {o.name: o.value for o in result.outcomes}
    assert outcomes["accepted"] == 1 and set(outcomes) == {"accepted", "declined", "exited", "open"}
    assert sum(h.value for h in result.per_hour_utc) == result.sessions


def test_translation_is_stored_and_failure_preserves_original(
    client: TestClient, reseed, monkeypatch
) -> None:
    sid = uuid.UUID(
        client.post("/sessions", json={"qr_token": QR, "device_id": str(uuid.uuid4())}).json()["session_id"]
    )

    async def exercise(db):
        monkeypatch.setattr(
            trace, "sessionmaker", lambda: async_sessionmaker(db.bind, expire_on_commit=False)
        )
        hub = MerchantHub()
        hub.translator = FakeTranslator()
        msg = await trace.record_message(
            db, hub, sid, channel="customer", speaker="customer", text="hello", language="te-IN"
        )
        await asyncio.gather(*hub.translation_tasks)
        await db.refresh(msg)
        assert msg.text == "hello" and msg.text_translated == "[en-IN] hello"

        class Broken:
            async def translate(self, text, source, target):
                raise RuntimeError("unavailable")

        hub.translator = Broken()
        failed = await trace.record_message(
            db, hub, sid, channel="customer", speaker="customer", text="retry"
        )
        await asyncio.gather(*hub.translation_tasks)
        await db.refresh(failed)
        assert failed.text == "retry" and failed.text_translated is None
        assert await db.get(Message, failed.id)

    run_db(exercise)


def test_translation_rejects_changed_size_or_amount(client: TestClient, reseed, monkeypatch) -> None:
    sid = uuid.UUID(
        client.post("/sessions", json={"qr_token": QR, "device_id": str(uuid.uuid4())}).json()["session_id"]
    )

    async def exercise(db):
        monkeypatch.setattr(
            trace, "sessionmaker", lambda: async_sessionmaker(db.bind, expire_on_commit=False)
        )
        hub = MerchantHub()

        class IncorrectTranslation:
            async def translate(self, text, source, target):
                return "मुझे N आकार की शर्ट ₹900 में चाहिए।"

        hub.translator = IncorrectTranslation()
        msg = await trace.record_message(
            db,
            hub,
            sid,
            channel="customer",
            speaker="customer",
            text="నాకు M size shirt ₹800 కావాలి",
            language="te-IN",
        )
        await asyncio.gather(*hub.translation_tasks)
        await db.refresh(msg)
        assert msg.text_translated is None
        assert "M size" in msg.text and "₹800" in msg.text

    run_db(exercise)
