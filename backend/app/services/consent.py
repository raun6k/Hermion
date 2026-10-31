"""One customer confirmation before anything enters the basket. Spec: docs/engine.md#basket-consent.

The server owns this state (`sessions.consent`), not the LLM:
  awaiting   price agreed; Hermion asks "shall I add it?"
  granted    one clear yes on a later turn; `add_to_basket` is now allowed for that evaluation
Anything else (a question, a new offer, a different item) clears it.

Voice and keypad follow the same one-yes rule. "I'll take it" (buy_now) may grant outright,
but only when the customer's own words say so; a model flag alone never grants consent.
"""

import re
import uuid
from contextvars import ContextVar
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Message, Session
from app.schemas.common import AppError

# Set per customer turn: True when the words came from the microphone (defaults to the strict path).
voice_turn: ContextVar[bool] = ContextVar("voice_turn", default=True)
# The customer's own words this turn: a buy_now flag from the model only counts if these agree.
turn_text: ContextVar[str] = ContextVar("turn_text", default="")

_STRONG = {
    # English + romanized Indic
    "yes", "yeah", "yep", "yup", "sure", "haan", "han", "haanji", "ji", "avunu", "avnu", "sare", "houdu",
    "howdu", "aam", "amam", "hanji", "kar", "karo", "kardo",
    # native scripts
    "हाँ", "हां", "जी", "ठीक", "అవును", "సరే", "ಹೌದು", "ಸರಿ", "ஆம்", "சரி", "അതെ", "ശരി", "હા", "ਹਾਂ", "হ্যাঁ", "ହଁ",
}  # fmt: skip
_WEAK = {"ok", "okay", "okey", "theek", "thik", "fine"}  # a yes only to a direct "shall I add it?"
_ACTION = re.compile(r"\b(add|take|buy|pack|confirm|done|deal|book)\b|ले\s?लो|कर\s?दो", re.IGNORECASE)
_NO = re.compile(
    r"\b(no|not|nahi|nahin|nope|wait|stop|but|how|what|why|when|which|kitna|kya|cancel|dont|don't)\b"
    r"|नहीं|नही|रुको|కాదు|వద్దు|ಬೇಡ|வேண்டாம்|[?？]",
    re.IGNORECASE,
)
_WORD = re.compile(r"[\wऀ-෿']+", re.UNICODE)


def says_take_it(text: str) -> bool:
    """The customer's own words commit to buying ("I'll take it", "pack it", "add it"), with no doubt."""
    return bool(_ACTION.search(text)) and not _NO.search(text)


def is_clear_yes(text: str, asked: bool) -> bool:
    """Strict: an agreement with no question, negation or new topic. Filler ("hmm", "acha") never counts;
    "ok" counts only when Hermion's last message asked, and only as a short reply."""
    if _NO.search(text):
        return False
    words = [w.lower() for w in _WORD.findall(text)]
    if not words or len(words) > 6:
        return False
    strong = any(w in _STRONG for w in words)
    action = bool(_ACTION.search(text))
    weak = any(w in _WEAK for w in words)
    if strong or action:
        return True
    return weak and asked and len(words) <= 3


async def customer_turns(db: AsyncSession, session_id: uuid.UUID) -> int:
    return (
        await db.scalar(
            select(func.count())
            .select_from(Message)
            .where(
                Message.session_id == session_id, Message.channel == "customer", Message.speaker == "customer"
            )
        )
        or 0
    )


async def open_consent(
    db: AsyncSession, session: Session, evaluation_id: uuid.UUID, buy_now: bool = False
) -> str:
    """A price was agreed: wait for one customer confirmation on a later turn.
    "I'll take it" grants the add outright, but only when the customer's own words say so:
    the model's buy_now flag alone never adds anything. Returns the stage."""
    granted = buy_now and says_take_it(turn_text.get())
    session.consent = {
        "stage": "granted" if granted else "awaiting",
        "evaluation_id": str(evaluation_id),
        "turn": await customer_turns(db, session.session_id),
        "asked": False,
    }
    await db.commit()
    return session.consent["stage"]


async def clear(db: AsyncSession, session: Session) -> None:
    if session.consent is not None:
        session.consent = None
        await db.commit()


async def advance(db: AsyncSession, session: Session, text: str) -> dict[str, Any] | None:
    """Run at the start of each customer turn with the customer's words."""
    c = session.consent
    if not c:
        return None
    turn = await customer_turns(db, session.session_id)
    if turn <= c["turn"]:
        return c
    if c["stage"] == "granted" or not is_clear_yes(text, bool(c.get("asked"))):
        session.consent = None
    else:
        # The same single clear yes is enough on voice and keypad. Legacy `confirming` sessions
        # also reach this branch, so their next clear yes is honored after an upgrade.
        session.consent = {**c, "stage": "granted", "turn": turn}
    await db.commit()
    return session.consent


async def mark_asked(db: AsyncSession, session: Session, reply: str) -> None:
    c = session.consent
    if c and c["stage"] == "awaiting" and re.search(r"[?？]", reply):
        session.consent = {**c, "asked": True}
        await db.commit()


async def require_granted(db: AsyncSession, session: Session, evaluation_id: uuid.UUID) -> None:
    c = session.consent
    if not c or c["stage"] != "granted" or c["evaluation_id"] != str(evaluation_id):
        raise AppError(
            "CUSTOMER_CONFIRMATION_REQUIRED",
            "Ask the customer to confirm the item and price, and add it after one clear yes.",
            409,
        )
