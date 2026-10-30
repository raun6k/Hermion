"""Bundle suggestion. Spec: docs/engine.md#concession-policy (suggest_bundle)."""

from app.engine.types import Evaluation, NegotiationContext, OfferItem, ProductTerms


def suggest_bundle(
    products: dict[str, ProductTerms], items: list[OfferItem], ctx: NegotiationContext
) -> Evaluation | None:
    raise NotImplementedError
