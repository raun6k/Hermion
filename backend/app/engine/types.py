"""Engine value types. Pure data; no I/O. Spec: docs/engine.md."""

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

MAX_ROUNDS = 4


class Decision(StrEnum):
    accept = "accept"
    counter = "counter"
    reject = "reject"


class OfferScope(StrEnum):
    per_unit = "per_unit"
    line = "line"
    basket = "basket"


class ReasonCode(StrEnum):
    ACCEPTABLE = "ACCEPTABLE"
    COUNTER = "COUNTER"
    FINAL_OFFER = "FINAL_OFFER"
    ROUNDS_EXHAUSTED = "ROUNDS_EXHAUSTED"
    FIXED_PRICE = "FIXED_PRICE"
    OUT_OF_STOCK = "OUT_OF_STOCK"
    INSUFFICIENT_STOCK = "INSUFFICIENT_STOCK"
    UNKNOWN_PRODUCT = "UNKNOWN_PRODUCT"
    BUNDLE_NOT_ALLOWED = "BUNDLE_NOT_ALLOWED"
    INVALID_OFFER = "INVALID_OFFER"
    OFFER_ABOVE_LISTED = "OFFER_ABOVE_LISTED"
    PROPOSAL_BELOW_FLOOR = "PROPOSAL_BELOW_FLOOR"
    CLOSING_BELOW_TARGET = "CLOSING_BELOW_TARGET"
    HELD_FOR_MORE = "HELD_FOR_MORE"  # the offer was acceptable, Hermion countered higher to win more


@dataclass(frozen=True)
class ProductTerms:
    """Everything the engine needs about one product (incl. private fields)."""

    product_id: str
    listed_price: Decimal
    target_price: Decimal | None
    minimum_price: Decimal
    available_stock: int
    negotiable: bool


@dataclass(frozen=True)
class OfferItem:
    product_id: str
    qty: int


@dataclass(frozen=True)
class MandateRule:
    product_id: str
    settle_at: Decimal
    min_qty: int | None = None
    with_product_id: str | None = None


@dataclass(frozen=True)
class LinePrice:
    product_id: str
    qty: int
    line_total: Decimal


@dataclass(frozen=True)
class NegotiationContext:
    """Session facts the services layer derives from the DB before each evaluation."""

    rounds: dict[str, int]  # product_id -> evaluations so far (before this one)
    basket_product_ids: frozenset[str] = frozenset()
    clear_stock: frozenset[str] = frozenset()
    preserve_stock: frozenset[str] = frozenset()
    mandate_rules: tuple[MandateRule, ...] = ()
    bundle_allowed: bool = False
    last_counter: tuple[LinePrice, ...] = field(default_factory=tuple)
    escalation_mode: str = "serious"  # never | serious | rare | when_close
    escalation_gap_pct: int = 5
    escalations_used: int = 0
    customer_serious: bool = True  # not lowballing (services/behavior); gates the `serious` escalation


@dataclass(frozen=True)
class Evaluation:
    decision: Decision
    reason_code: ReasonCode
    round: int
    final: bool
    price: Decimal | None = None
    line_prices: tuple[LinePrice, ...] = ()
    threshold: Decimal | None = None  # merchant-only; never shown to customer or LLM
    signals: tuple[str, ...] = ()  # which of buy_now / qty / basket / clear_stock raised the round
    mandate_applied: bool = False
    escalation_eligible: bool = False  # offer is just below the floor and the merchant allows a check
    headroom: str | None = None  # high|medium|low|none; the only range signal the LLM sees
    acceptable: bool = False  # on HELD_FOR_MORE: the customer's own offer could still be accepted
