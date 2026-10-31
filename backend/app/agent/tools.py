"""Tool schemas exposed to the LLM and their dispatch to services. Spec: docs/engine.md#tools.

`session_id` is injected server-side (ToolContext) and never appears in a tool schema. Tool results
carry public fields only: whole-rupee strings, decisions, no thresholds.
"""

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SessionState
from app.engine.types import OfferItem, OfferScope, ReasonCode
from app.schemas.common import AppError
from app.schemas.public import BasketPublic
from app.services import basket, catalog, consent, mandates, offers, price_checks, sessions
from app.services.hub import Hubs

TOOL_NAMES = (
    "search_products",
    "evaluate_offer",
    "suggest_bundle",
    "suggest_addons",
    "ask_shopkeeper",
    "add_to_basket",
    "remove_from_basket",
    "send_basket_to_shopkeeper",
    "propose_mandate",
)

S = SessionState
STATE_TOOLS: dict[SessionState, tuple[str, ...]] = {
    S.intro: (),
    S.discovery: ("search_products", "evaluate_offer", "suggest_addons"),
    S.negotiating: (
        "search_products",
        "evaluate_offer",
        "suggest_bundle",
        "suggest_addons",
        "ask_shopkeeper",
        "add_to_basket",
        "remove_from_basket",
        "send_basket_to_shopkeeper",
    ),
    S.pending_merchant: (),
    S.briefing: ("search_products", "propose_mandate"),
    S.in_person: (),
    S.accepted: (),
    S.declined: (),
    S.exited: (),
}

# Engine outcomes that are tool errors (nothing to negotiate), vs. normal decisions with a price.
ERROR_REASONS = frozenset(
    {
        ReasonCode.UNKNOWN_PRODUCT,
        ReasonCode.OUT_OF_STOCK,
        ReasonCode.INSUFFICIENT_STOCK,
        ReasonCode.BUNDLE_NOT_ALLOWED,
        ReasonCode.INVALID_OFFER,
        ReasonCode.OFFER_ABOVE_LISTED,
    }
)


# ---- argument models (validated server-side; the JSON schemas below are what the LLM sees) ----


class SearchArgs(BaseModel):
    query: str = Field(min_length=1, max_length=200)


class ItemArg(BaseModel):
    product_id: str
    qty: int = Field(default=1, ge=1, le=99)


class EvaluateArgs(BaseModel):
    items: list[ItemArg] = Field(min_length=1, max_length=6)
    offered_amount: Decimal = Field(gt=0, lt=10_000_000)
    offer_scope: Literal["per_unit", "line", "basket"] = "per_unit"
    buy_now: bool = False
    proposed_price: Decimal | None = Field(default=None, gt=0, lt=10_000_000)


class BundleArgs(BaseModel):
    product_ids: list[str] = Field(min_length=2, max_length=6)


class AddonArgs(BaseModel):
    product_ids: list[str] = Field(min_length=1, max_length=6)


class EvaluationArgs(BaseModel):
    evaluation_id: uuid.UUID


class RemoveArgs(BaseModel):
    product_id: str


def _fn(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required},
        },
    }


_ITEM = {
    "type": "object",
    "properties": {
        "product_id": {"type": "string", "description": "product_id from search_products"},
        "qty": {"type": "integer", "description": "number of pieces, default 1"},
    },
    "required": ["product_id"],
}

_SCHEMAS: dict[str, dict[str, Any]] = {
    "search_products": _fn(
        "search_products",
        "Find products in the shop by name, colour, size or local word. Returns up to 5 variants with "
        "listed price, stock band (in/low/out) and whether the price is negotiable.",
        {"query": {"type": "string", "description": "what the customer asked for, e.g. 'blue shirt M'"}},
        ["query"],
    ),
    "evaluate_offer": _fn(
        "evaluate_offer",
        "Ask the pricing engine about a customer's offer. Returns decision accept/counter/reject, price, "
        "reason_code, round, final, headroom (high/medium/low/none: how much you may still concede) and "
        "customer_read with guidance. The only source of prices. Pass proposed_price to choose your own "
        "counter; the engine keeps it inside the shop's safe range and may replace it.",
        {
            "items": {
                "type": "array",
                "items": _ITEM,
                "description": "the products and quantities offered on",
            },
            "offered_amount": {
                "type": "string",
                "description": "the customer's number in whole rupees, digits only, e.g. '700'",
            },
            "offer_scope": {
                "type": "string",
                "enum": ["per_unit", "line", "basket"],
                "description": "per_unit: price for one piece. line: total for the quantity of one product. basket: one total for several products.",
            },
            "buy_now": {
                "type": "boolean",
                "description": "true only if the customer clearly says they will take it right now",
            },
            "proposed_price": {
                "type": "string",
                "description": "optional: the total in whole rupees you want to counter with, digits only. Pass it to hold out for more even when the customer's offer is acceptable; omit it to take the customer's offer if the shop can. Start high and concede in shrinking steps, guided by headroom.",
            },
        },
        ["items", "offered_amount"],
    ),
    "suggest_bundle": _fn(
        "suggest_bundle",
        "Get the shop's price for taking several products together (2 or more). Use it to pitch a pair.",
        {"product_ids": {"type": "array", "items": {"type": "string"}}},
        ["product_ids"],
    ),
    "suggest_addons": _fn(
        "suggest_addons",
        "Get up to 2 products worth offering: 'upgrade' is a better version of a product the customer is "
        "considering (works before it is in the basket), 'pairs_with' goes with a product already in the basket. "
        "Ask about at most one, as a question; never add it yourself.",
        {
            "product_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "products the customer is considering or already has in the basket",
            }
        },
        ["product_ids"],
    ),
    "ask_shopkeeper": _fn(
        "ask_shopkeeper",
        "Ask the shopkeeper about one offer, only when the evaluate_offer result says shopkeeper_check_possible. "
        "Use it at most once; afterwards tell the customer you are checking and quote no price.",
        {"evaluation_id": {"type": "string", "description": "evaluation_id of that evaluate_offer result"}},
        ["evaluation_id"],
    ),
    "add_to_basket": _fn(
        "add_to_basket",
        "Put an accepted evaluation in the customer's basket (replaces an earlier line for the same product).",
        {
            "evaluation_id": {
                "type": "string",
                "description": "evaluation_id of an accepted evaluate_offer or suggest_bundle result",
            }
        },
        ["evaluation_id"],
    ),
    "remove_from_basket": _fn(
        "remove_from_basket",
        "Remove a product from the basket.",
        {"product_id": {"type": "string"}},
        ["product_id"],
    ),
    "send_basket_to_shopkeeper": _fn(
        "send_basket_to_shopkeeper",
        "Send the customer's basket to the shopkeeper for approval (same as the customer pressing Send). "
        "Only when the customer clearly asks for it and the basket is not empty.",
        {},
        [],
    ),
    "propose_mandate": _fn(
        "propose_mandate",
        "Turn the shopkeeper's instruction into pricing rules for this customer. The shopkeeper reviews and "
        "confirms before anything changes. settle_at is the price per piece the shopkeeper is happy to settle at.",
        {
            "rules": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "product_id": {"type": "string"},
                        "settle_at": {"type": "string", "description": "price per piece in rupees, digits"},
                        "min_qty": {
                            "type": "integer",
                            "description": "only when at least this many pieces are bought",
                        },
                        "with_product_id": {
                            "type": "string",
                            "description": "only when this other product is bought too",
                        },
                    },
                    "required": ["product_id", "settle_at"],
                },
            }
        },
        ["rules"],
    ),
}


def tool_schemas(state: str | SessionState) -> list[dict[str, Any]]:
    """OpenAI-format tool definitions allowed in this session state (stable order, byte-identical)."""
    names = STATE_TOOLS.get(SessionState(state), ())
    return [_SCHEMAS[n] for n in names]


# ---- dispatch ---------------------------------------------------------------------


@dataclass(frozen=True)
class ToolContext:
    db: AsyncSession
    hubs: Hubs
    session_id: uuid.UUID  # injected here, never chosen by the LLM


def _basket_json(public: BasketPublic) -> dict[str, Any]:
    return {
        "basket": [
            {
                "product_id": ln.product_id,
                "product_name": ln.product_name,
                "qty": ln.qty,
                "line_total": offers.rupees(ln.line_total),
            }
            for ln in public.lines
        ],
        "total": offers.rupees(public.total),
    }


async def dispatch(ctx: ToolContext, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Run one tool call. Never raises: failures come back as `{"error": CODE}` for the LLM to explain."""
    try:
        session = await sessions.get_session(ctx.db, ctx.session_id)
        if name not in TOOL_NAMES or name not in STATE_TOOLS.get(session.state, ()):
            return {"error": "TOOL_NOT_ALLOWED"}
        return await _run(ctx, name, arguments)
    except ValidationError as exc:
        return {"error": "INVALID_ARGUMENTS", "detail": str(exc.errors()[0]["msg"])}
    except AppError as exc:
        return {"error": exc.code}


async def _run(ctx: ToolContext, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    db, hubs, sid = ctx.db, ctx.hubs, ctx.session_id
    match name:
        case "search_products":
            args = SearchArgs.model_validate(arguments)
            owner = await sessions.get_session(db, sid)
            found = await catalog.search_products(db, args.query, owner.merchant_id)
            return {
                "products": [
                    {**p.model_dump(mode="json"), "listed_price": offers.rupees(p.listed_price)}
                    for p in found
                ]
            }
        case "evaluate_offer":
            args = EvaluateArgs.model_validate(arguments)
            result = await offers.evaluate(
                db,
                hubs,
                sid,
                [OfferItem(i.product_id, i.qty) for i in args.items],
                args.offered_amount,
                OfferScope(args.offer_scope),
                args.buy_now,
                args.proposed_price,
            )
            if result["reason_code"] in ERROR_REASONS:
                if result["reason_code"] == ReasonCode.OFFER_ABOVE_LISTED:
                    return {"error": "OFFER_ABOVE_LISTED", "detail": "Ask the customer to clarify the offer."}
                return {"error": result["reason_code"]}
            return result
        case "suggest_bundle":
            args = BundleArgs.model_validate(arguments)
            bundle = await offers.suggest_bundle(db, hubs, sid, args.product_ids)
            return (
                bundle
                if bundle is not None
                else {"suggestion": None, "message": "No valid multi-item quote for those products."}
            )
        case "suggest_addons":
            args = AddonArgs.model_validate(arguments)
            return {"addons": await catalog.suggest_addons(db, sid, args.product_ids)}
        case "ask_shopkeeper":
            args = EvaluationArgs.model_validate(arguments)
            return await price_checks.ask(db, hubs, sid, args.evaluation_id)
        case "add_to_basket":
            args = EvaluationArgs.model_validate(arguments)
            session = await sessions.get_session(db, sid)
            await consent.require_granted(db, session, args.evaluation_id)
            result = _basket_json(await basket.add_from_evaluation(db, hubs, sid, args.evaluation_id))
            await consent.clear(db, session)
            return result
        case "remove_from_basket":
            args = RemoveArgs.model_validate(arguments)
            return _basket_json(await basket.remove(db, hubs, sid, args.product_id))
        case "send_basket_to_shopkeeper":
            session, public = await basket.confirm(db, hubs, sid)
            return {"sent": True, "state": session.state.value, **_basket_json(public)}
        case "propose_mandate":
            parsed = mandates.MandateArgs.model_validate(arguments)
            mandate, proposal = await mandates.propose(db, hubs, sid, parsed)
            return {
                "mandate_id": str(mandate.id),
                "readable": proposal.readable,
                "limited_product_ids": proposal.limited_product_ids,
                "note": "The shopkeeper must confirm before this applies."
                + (
                    " Some prices were outside the shop's catalog limits and were held at the limit."
                    if proposal.limited_product_ids
                    else ""
                ),
            }
    return {"error": "TOOL_NOT_ALLOWED"}
