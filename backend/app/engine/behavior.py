"""Customer behaviour read from the offers history. Spec: docs/engine.md#customer-read.

Pure: the service turns offers and messages into `BehaviorFeatures`; this module classifies them and
returns wording guidance for the prompt. No numbers cross into the guidance.
"""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class Profile(StrEnum):
    lowballer = "lowballer"
    value_seeker = "value_seeker"
    ready_to_buy = "ready_to_buy"
    browsing = "browsing"


@dataclass(frozen=True)
class BehaviorFeatures:
    offers: int  # customer offers so far, this one included
    opening_ratio: Decimal | None  # first offer / listed total
    last_step_ratio: Decimal | None  # latest rise between their offers / listed total
    repeats: int  # times they repeated the same number
    hesitation: int  # comparison or "let me think" messages
    qty_or_bundle: bool
    buy_now: bool
    walk_away: bool  # "I'll check elsewhere", "forget it"


def classify(f: BehaviorFeatures) -> Profile:
    if f.walk_away or (f.offers == 0 and f.hesitation > 0) or f.repeats >= 2:
        return Profile.browsing
    if f.buy_now or f.qty_or_bundle and f.offers >= 1:
        return Profile.ready_to_buy
    if f.opening_ratio is not None and f.opening_ratio < Decimal("0.6"):
        return Profile.lowballer
    if (
        f.offers >= 2
        and f.opening_ratio is not None
        and f.opening_ratio >= Decimal("0.85")
        and (f.last_step_ratio or Decimal(0)) <= Decimal("0.03")
    ):
        return Profile.ready_to_buy
    return Profile.value_seeker


def guidance(profile: Profile, walk_away: bool) -> str:
    """How hard to hold and how to concede, in words only."""
    if walk_away:
        return (
            "The customer is leaving: do not push. Be warm, give your best offer once, and let them go "
            "gracefully."
        )
    return _GUIDANCE[profile]


_GUIDANCE = {
    Profile.lowballer: (
        "Lowballing: stay close to the listed price, give value reasons, concede in small steps and ask "
        "for something in return each time."
    ),
    Profile.value_seeker: (
        "Value-seeking: explain what they get, concede in shrinking steps, trade each concession for "
        "quantity, a bundle or buying now."
    ),
    Profile.ready_to_buy: (
        "Ready to buy: hold firm near the current price, make closing easy, and do not give away more "
        "than needed."
    ),
    Profile.browsing: (
        "Just browsing: keep it light, one clear offer, a slightly bigger step is fine to win them over; "
        "never pressure."
    ),
}
