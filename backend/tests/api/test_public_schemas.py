"""Invariant: nothing customer-facing can carry a private field (docs/architecture.md#invariants)."""

import typing

from pydantic import BaseModel

from app.schemas import events, public

PRIVATE = {"target_price", "minimum_price", "unit_cost", "threshold", "contribution"}


def _fields(model: type[BaseModel], seen: set[type] | None = None) -> set[str]:
    seen = seen if seen is not None else set()
    if model in seen:
        return set()
    seen.add(model)
    names = set(model.model_fields)
    for f in model.model_fields.values():
        for arg in [f.annotation, *typing.get_args(f.annotation)]:
            for inner in [arg, *typing.get_args(arg)]:
                if isinstance(inner, type) and issubclass(inner, BaseModel):
                    names |= _fields(inner, seen)
    return names


def _models(module) -> list[type[BaseModel]]:
    return [v for v in vars(module).values() if isinstance(v, type) and issubclass(v, BaseModel)]


def test_public_schemas_have_no_private_fields() -> None:
    for model in _models(public):
        assert not PRIVATE & _fields(model), model.__name__


def test_customer_events_have_no_private_fields() -> None:
    for model in events.CUSTOMER_OUTBOUND_MODELS:
        assert not PRIVATE & _fields(model), model.__name__
