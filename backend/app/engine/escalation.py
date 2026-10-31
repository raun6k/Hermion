"""When Hermion may ask the shopkeeper. Spec: docs/engine.md#escalation."""

from decimal import Decimal

CAP_PER_SESSION = 2


def should_escalate(
    mode: str,
    offered_total: Decimal,
    floor_total: Decimal,
    gap_pct: int,
    high_intent: bool,
    used: int,
    serious: bool = True,
) -> bool:
    """True for a below-floor offer the shopkeeper may want to answer, within the per-session cap.

    `serious` (default): any below-floor offer from a customer who is not lowballing. `rare`: close to the
    floor (within `gap_pct`) and high intent (buy now, quantity >= 2, or a bundle). `when_close`: close
    to the floor. `never` is never.
    """
    if mode == "never" or used >= CAP_PER_SESSION:
        return False
    if offered_total >= floor_total or floor_total <= 0:
        return False
    if mode == "serious":
        return serious
    if (floor_total - offered_total) * 100 > floor_total * gap_pct:
        return False
    return high_intent or mode == "when_close"
