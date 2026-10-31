"""Output guard: every amount Hermion says must be engine-approved. Spec: docs/engine.md#output-guard.

Before TTS the reply is scanned for amounts: numbers next to a rupee marker, any number >= 100
(sizes and quantities pass), and amounts spelled out in words. Each must be in the allowed set, built
from this session's engine log, listed prices, basket total and the customer's own offers.
"""

import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

# A magnitude word ("sau", "వందలు") whose number could not be read. It never equals an allowed amount,
# so the guard treats the reply as a violation rather than let an unreadable price through.
UNPARSEABLE = Decimal(-1)
AMOUNT_FLOOR = Decimal(100)

_MARKER_BEFORE = re.compile(r"(?:^|[\s(\-:])(?:₹|₨|rs\.?|inr|रु\.?|रू)\s*$", re.IGNORECASE)
_CURRENCY_WORDS = {
    "rupee", "rupees", "rupaye", "rupaya", "rupayi", "rupai", "rs", "inr", "रुपये", "रुपया", "रुपए", "रूपये",
    "రూపాయలు", "రూపాయి", "రూపాయల", "ரூபாய்", "ரூபாய", "ರೂಪಾಯಿ", "ರೂಪಾಯಿಗಳು", "രൂപ", "টাকা", "ટકા", "રૂપિયા",
    "ਰੁਪਏ", "ਰੁਪਈਏ", "रुपयांना", "रुपयात", "ଟଙ୍କା", "bucks",
}  # fmt: skip

# ---- number words -----------------------------------------------------------------
# kind: u = unit/tens (adds), h = hundred, t = thousand, l = lakh, c = crore. Units and tens are listed
# for English, Hindi (Devanagari + romanized) and Telugu; other languages are caught by their
# magnitude word and flagged UNPARSEABLE.
_WORDS: dict[str, tuple[str, int]] = {}


def _add(kind: str, value: int, *words: str) -> None:
    for w in words:
        _WORDS[w] = (kind, value)


for _v, _ws in enumerate(
    [
        ("one",), ("two",), ("three",), ("four", "fourty"), ("five",), ("six",), ("seven",), ("eight",), ("nine",),
        ("ten",), ("eleven",), ("twelve",), ("thirteen",), ("fourteen",), ("fifteen",), ("sixteen",),
        ("seventeen",), ("eighteen",), ("nineteen",), ("twenty",),
    ],
    start=1,
):  # fmt: skip
    _add("u", _v, *_ws)
_add("u", 30, "thirty")
_add("u", 40, "forty")
_add("u", 50, "fifty")
_add("u", 60, "sixty")
_add("u", 70, "seventy")
_add("u", 80, "eighty")
_add("u", 90, "ninety")
_add("h", 100, "hundred", "hundreds")
_add("t", 1000, "thousand")
_add("l", 100000, "lakh", "lakhs", "lac", "lacs")
_add("c", 10000000, "crore", "crores")

# Hindi, Devanagari
for _v, _ws in enumerate(
    ["एक", "दो", "तीन", "चार", "पाँच पांच", "छह छः छे", "सात", "आठ", "नौ", "दस"], start=1
):  # fmt: skip
    _add("u", _v, *_ws.split())
_add("u", 20, "बीस")
_add("u", 25, "पच्चीस")
_add("u", 30, "तीस")
_add("u", 40, "चालीस")
_add("u", 50, "पचास")
_add("u", 60, "साठ")
_add("u", 70, "सत्तर")
_add("u", 75, "पचहत्तर")
_add("u", 80, "अस्सी")
_add("u", 90, "नब्बे")
_add("h", 100, "सौ", "सौं")
_add("t", 1000, "हज़ार", "हजार", "हज़ारों")
_add("l", 100000, "लाख")
# Hindi, romanized
for _v, _ws in enumerate(
    ["ek", "do", "teen", "char", "paanch panch", "chhe chhah chhey", "saat", "aath", "nau", "das"], start=1
):  # fmt: skip
    _add("u", _v, *_ws.split())
_add("u", 20, "bees")
_add("u", 25, "pachchis", "pacchis")
_add("u", 30, "tees")
_add("u", 40, "chalis", "chaalis")
_add("u", 50, "pachaas", "pachas", "pachas")
_add("u", 60, "saath")
_add("u", 70, "sattar")
_add("u", 75, "pachattar", "pachhattar")
_add("u", 80, "assi")
_add("u", 90, "nabbe")
_add("h", 100, "sau")
_add("t", 1000, "hazaar", "hazar", "hajaar", "hajar")
# Telugu
for _v, _w in enumerate(["ఒకటి", "రెండు", "మూడు", "నాలుగు", "ఐదు", "ఆరు", "ఏడు", "ఎనిమిది", "తొమ్మిది", "పది"], start=1):
    _add("u", _v, _w)
_add("u", 20, "ఇరవై")
_add("u", 30, "ముప్పై")
_add("u", 40, "నలభై")
_add("u", 50, "యాభై", "ఏభై")
_add("u", 60, "అరవై")
_add("u", 70, "డెబ్బై")
_add("u", 80, "ఎనభై")
_add("u", 90, "తొంభై")
_add("h", 100, "వంద", "వందలు", "వందల")
_add("t", 1000, "వెయ్యి", "వేల", "వేలు")
_add("l", 100000, "లక్ష", "లక్షలు")

# Magnitude words in languages without unit tables: present => an amount we cannot read.
_UNREADABLE_MAGNITUDES = frozenset(
    ["நூறு", "நூற்று", "ஆயிரம்", "லட்சம்", "ನೂರು", "ನೂರಾ", "ಸಾವಿರ", "ಲಕ್ಷ", "നൂറു", "നൂറ്", "ആയിരം", "ലക്ഷം", "শো", "শত", "হাজার", "লাখ", "સો", "સૌ", "હજાર", "લાખ", "ਸੌ", "ਹਜ਼ਾਰ", "ਲੱਖ", "शे", "शंभर", "हजार", "ଶହ", "ହଜାର"]
)  # fmt: skip
_MULTIPLIERS = {k: v for k, (kind, v) in _WORDS.items() if kind in "tlc"}

_TOKEN_SPLIT = re.compile(r"[\s,;:!?()\[\]\"'“”‘’।॥/]+")
_NUMBER = re.compile(r"(?<![\w.,])(\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?)")

# A measurement such as "5000 mAh" or "256 GB" is a product fact, not a price. It is exempt only when the
# same number and unit appear in the merchant's facts for a product (see `spec_mentions`) and no rupee
# marker precedes it, so "₹5000" stays an amount.
_SPEC_UNITS = (
    "mah", "gb", "tb", "mb", "w", "watt", "watts", "kw", "v", "volt", "volts", "hz", "mm", "cm", "inch",
    "inches", "ft", "feet", "kg", "g", "gm", "gsm", "l", "litre", "litres", "liter", "liters", "ml", "rpm",
    "mp", "cc", "tc", "thread", "threads", "nits", "dpi",
)  # fmt: skip
_SPEC_MENTION = re.compile(
    r"(?<![\w.,])(\d[\d,]*(?:\.\d+)?)\s*("
    + "|".join(sorted(_SPEC_UNITS, key=len, reverse=True))
    + r")(?!\w)",
    re.IGNORECASE,
)


def _ascii_digits(text: str) -> str:
    """Map every Unicode decimal digit (Devanagari, Telugu, ...) to ASCII."""
    return "".join(
        str(unicodedata.digit(ch)) if ch.isdigit() and ch.isascii() is False else ch for ch in text
    )


def _has_marker_before(text: str, start: int) -> bool:
    return _MARKER_BEFORE.search(text[max(0, start - 8) : start]) is not None


def _digit_amounts(text: str) -> list[Decimal]:
    out: list[Decimal] = []
    for m in _NUMBER.finditer(text):
        try:
            value = Decimal(m.group(1).replace(",", ""))
        except InvalidOperation:
            continue
        after = text[m.end() : m.end() + 24].lower().lstrip()
        word = _TOKEN_SPLIT.split(after, maxsplit=1)[0].rstrip(".")
        marker = True if after.startswith("/-") else word in _CURRENCY_WORDS
        mult = _MULTIPLIERS.get(word)
        if mult or word in _UNREADABLE_MAGNITUDES:
            value = value * mult if mult else UNPARSEABLE
        elif word in {"k", "hazar"}:
            value *= 1000
        if value >= AMOUNT_FLOOR or marker or _has_marker_before(text, m.start()) or value == UNPARSEABLE:
            out.append(value)
    return out


def _word_amounts(text: str) -> list[Decimal]:
    """Amounts spelled out ("eight hundred", "आठ सौ", "aath sau"). Digits are handled elsewhere."""
    tokens = [t for t in _TOKEN_SPLIT.split(text.lower()) if t]
    out: list[Decimal] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i].rstrip(".")
        if tok in _UNREADABLE_MAGNITUDES:
            out.append(UNPARSEABLE)
            i += 1
            continue
        if tok not in _WORDS:
            i += 1
            continue
        # Read a run of number words (an "and" inside the run is a connector).
        total = current = 0
        magnitude = False
        j = i
        while j < len(tokens):
            t = tokens[j].rstrip(".")
            if t == "and" and j + 1 < len(tokens) and tokens[j + 1] in _WORDS and j > i:
                j += 1
                continue
            if t not in _WORDS:
                break
            kind, value = _WORDS[t]
            if kind == "u":
                current += value
            elif kind == "h":
                current = (current or 1) * 100
                magnitude = True
            else:
                total += (current or 1) * value
                current = 0
                magnitude = True
            j += 1
        amount = Decimal(total + current)
        prev = tokens[i - 1].rstrip(".") if i else ""
        nxt = tokens[j].rstrip(".") if j < len(tokens) else ""
        near_currency = nxt in _CURRENCY_WORDS or prev in _CURRENCY_WORDS or prev.endswith("₹")
        if magnitude or amount >= AMOUNT_FLOOR or near_currency:
            out.append(amount)
        i = max(j, i + 1)
    return out


_DIGITS_WITH_MAGNITUDE = re.compile(
    r"\d[\d,.]*(?:\s*(?:"
    + "|".join(re.escape(w) for w in sorted({*_MULTIPLIERS, *_UNREADABLE_MAGNITUDES}, key=len, reverse=True))
    + r")(?=[\s,.;:!?]|$))?",
    re.IGNORECASE,
)


def extract_amounts(text: str) -> list[Decimal]:
    """Amounts a reply states: rupee-marked numbers, numbers >= 100, and amounts written as words."""
    text = _ascii_digits(text)
    return _digit_amounts(text) + _word_amounts(_DIGITS_WITH_MAGNITUDE.sub(" ", text))


def _spec_key(number: str, unit: str) -> tuple[Decimal, str] | None:
    try:
        return Decimal(number.replace(",", "")), unit.lower()
    except InvalidOperation:
        return None


def spec_mentions(texts: Iterable[str]) -> frozenset[tuple[Decimal, str]]:
    """(number, unit) pairs written in product facts: names, pitch, selling points, specs."""
    out = set()
    for text in texts:
        for m in _SPEC_MENTION.finditer(_ascii_digits(text)):
            if key := _spec_key(m.group(1), m.group(2)):
                out.add(key)
    return frozenset(out)


def _drop_spec_mentions(text: str, specs: frozenset[tuple[Decimal, str]]) -> str:
    def keep_or_drop(m: re.Match[str]) -> str:
        if _has_marker_before(text, m.start()) or _spec_key(m.group(1), m.group(2)) not in specs:
            return m.group(0)
        return " "

    return _SPEC_MENTION.sub(keep_or_drop, text)


def check_reply(
    text: str, allowed: set[Decimal], specs: frozenset[tuple[Decimal, str]] = frozenset()
) -> list[Decimal]:
    """Return the amounts in `text` that are not allowed (empty list = pass)."""
    if specs:
        text = _drop_spec_mentions(_ascii_digits(text), specs)
    return [a for a in extract_amounts(text) if a not in allowed]


# ---- the allowed set --------------------------------------------------------------


@dataclass(frozen=True)
class GuardFacts:
    """What Hermion may say, as plain data the loop assembles from the DB each turn."""

    listed: Mapping[str, Decimal]  # product_id -> unit listed price, for products in play
    offers: Sequence[Mapping[str, Any]] = ()  # price + line_prices[{product_id, qty, line_total}]
    basket_total: Decimal | None = None
    customer_amounts: Iterable[Decimal] = field(default_factory=tuple)


def allowed_amounts(facts: GuardFacts) -> set[Decimal]:
    allowed: set[Decimal] = set(facts.listed.values())
    qtys: dict[str, set[int]] = {pid: {1} for pid in facts.listed}
    for offer in facts.offers:
        if (price := offer.get("price")) is not None:
            allowed.add(Decimal(str(price)))
        for lp in offer.get("line_prices") or ():
            total, qty = Decimal(str(lp["line_total"])), int(lp["qty"])
            allowed.add(total)
            qtys.setdefault(lp["product_id"], {1}).add(qty)
            if qty > 1 and total % qty == 0:
                allowed.add(total / qty)  # unit price is a display convenience
    for pid, unit in facts.listed.items():
        allowed.update(unit * q for q in qtys.get(pid, ()))
    if facts.basket_total is not None:
        allowed.add(facts.basket_total)
    allowed.update(facts.customer_amounts)
    return allowed


# ---- private shop data ------------------------------------------------------------

_WORD = re.compile(r"\w+", re.UNICODE)
_SHINGLE = 4  # words in a row copied from the shopkeeper's notes
_INTERNAL_TALK = re.compile(
    r"in the shop for a while|\b(?:old|slow[- ]moving|dead|excess|surplus|unsold)\s+stock\b"
    r"|\b(?:clear(?:ing)?|get rid of|offload)\b.{0,24}\b(?:stock|inventory|kurtas?)\b"
    r"|\bshop ?keeper(?:'s|’s)?\s+(?:instructions?|preferences?|notes?|goals?|mandate|rules)\b"
    r"|\b(?:my|the|these)\s+(?:instructions|guidelines|system prompt|private notes)\b"
    r"|\bsystem prompt\b|\b(?:minimum|target|cost)\s+price\b|\bunit cost\b|\bprofit margins?\b"
    r"|\b(?:shop ?keeper|owner|merchant)\s+(?:wants|needs|asked|told|instructed|prefers)\s+(?:me|to|us)\b",
    re.IGNORECASE | re.DOTALL,
)


def _shingles(text: str) -> set[tuple[str, ...]]:
    words = [w.lower() for w in _WORD.findall(text)]
    return {tuple(words[i : i + _SHINGLE]) for i in range(len(words) - _SHINGLE + 1)}


def leaks_private(reply: str, secrets: Iterable[str]) -> bool:
    """True when a reply repeats the shopkeeper's private notes or talks about the shop's internals."""
    if _INTERNAL_TALK.search(reply):
        return True
    copied = _shingles(reply)
    return any(copied & _shingles(secret) for secret in secrets)
