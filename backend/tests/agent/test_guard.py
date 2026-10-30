"""Output guard: amount extraction (digits, Indic digits, number words) and the allowed set."""

from decimal import Decimal as D

import pytest

from app.agent.guard import UNPARSEABLE, GuardFacts, allowed_amounts, check_reply, extract_amounts


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("The price is ₹850.", [850]),
        ("Rs. 1,100 for both", [1100]),
        ("₹5,00,000 only", [500000]),
        ("850 rupees", [850]),
        ("₹850.00", [850]),
        ("about 950 sir", [950]),
        ("Size 32, pack of 3, two shirts", []),  # sizes and quantities pass
        ("only ₹50 off", [50]),  # marked amounts count even below 100
        ("₹ 850", [850]),
        ("850/-", [850]),
        ("యూ ₹౮౫౦", [850]),  # Telugu digits
        ("मूल्य ₹८५० है", [850]),  # Devanagari digits
        ("1.5 lakh", [150000]),
        ("2 hazaar", [2000]),
        ("Thanks, see you at 7 pm", []),
        ("I can do 900 or 850", [900, 850]),
        ("yours 50", []),  # "rs" inside a word is not a marker
    ],
)
def test_digit_amounts(text: str, expected: list[int]) -> None:
    assert extract_amounts(text) == [D(x) for x in expected]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("eight hundred rupees", [800]),
        ("It is one thousand and fifty rupees", [1050]),
        ("two thousand", [2000]),
        ("seven hundred fifty", [750]),
        ("आठ सौ रुपये", [800]),
        ("सात सौ पचास", [750]),
        ("एक हज़ार", [1000]),
        ("aath sau", [800]),
        ("saat sau pachaas rupaye", [750]),
        ("ఎనిమిది వందలు", [800]),
        ("తొమ్మిది వందల యాభై", [950]),
        ("fifty rupees", [50]),
        ("do shirt chahiye", []),  # "do" alone is just a word
        ("two shirts and three belts", []),
        ("நூறு ரூபாய்", [UNPARSEABLE]),  # no unit table for Tamil: flagged, never passed
        ("ಎಂಟು ನೂರು", [UNPARSEABLE]),
    ],
)
def test_amounts_in_words(text: str, expected: list[int]) -> None:
    assert extract_amounts(text) == [D(x) for x in expected]


def test_check_reply_flags_only_unapproved_amounts() -> None:
    allowed = {D(950), D(900), D(1000)}
    assert check_reply("₹900 is the best I can do. The listed price is 1,000.", allowed) == []
    assert check_reply("I can do ₹850 for you.", allowed) == [D(850)]
    assert (
        check_reply("nine hundred rupees", allowed) == [D(900)]
        or check_reply("nine hundred rupees", allowed) == []
    )
    assert check_reply("eight hundred rupees", allowed) == [D(800)]
    assert check_reply("நூறு", allowed) == [UNPARSEABLE]  # unreadable amount fails closed
    assert check_reply("Sure, let me check.", allowed) == []


def test_allowed_amounts_from_engine_facts() -> None:
    facts = GuardFacts(
        listed={"SHIRT": D(1000), "BELT": D(500)},
        offers=[
            {
                "price": "1150",
                "line_prices": [
                    {"product_id": "SHIRT", "qty": 1, "line_total": "850"},
                    {"product_id": "BELT", "qty": 2, "line_total": "600"},
                ],
            },
            {"price": None, "line_prices": []},
        ],
        basket_total=D(1450),
        customer_amounts=[D(700)],
    )
    allowed = allowed_amounts(facts)
    assert {D(1000), D(500), D(1150), D(850), D(600), D(300), D(1450), D(700), D(1000)} <= allowed
    assert D(2000) not in allowed
    assert D(1000) in allowed and D(500) * 2 in allowed  # listed x qty seen in an offer
    assert check_reply("₹850 for the shirt, ₹300 each for belts", allowed) == []
    assert check_reply("₹750 for the shirt", allowed) == [D(750)]  # a minimum price would be caught


def test_private_numbers_are_caught_unless_legitimately_priced() -> None:
    private = {D(750), D(630)}  # minimum, cost
    allowed = allowed_amounts(GuardFacts(listed={"S": D(1000)}, offers=[{"price": "800"}]))
    leaked = [a for a in check_reply("My minimum is 750 and cost 630", allowed) if a in private]
    assert leaked == [D(750), D(630)]
