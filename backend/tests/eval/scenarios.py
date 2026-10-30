"""Scenario file schema (backend/seed/customer_scenarios.json). Test-only: `hidden_budget` is for the
harness and is never shown to Hermion."""

import json
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator

from app import languages

SCENARIOS_PATH = Path(__file__).resolve().parents[2] / "seed" / "customer_scenarios.json"


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    merchant_id: str
    language: str  # customer's language, Sarvam code
    messages: list[str]
    hidden_budget: Decimal | None = None
    tags: list[str] = []
    channel: Literal["customer", "briefing"] = "customer"
    setup: Literal["pending_basket"] | None = None  # briefing: a basket already sent for review
    exit_after: int | None = None  # customer taps End call after this many messages
    expect_deal: bool | None = None  # False: any accepted offer is a failure
    expect_final_state: str | None = None
    expect_mandate: list[dict[str, Any]] | None = None

    @field_validator("language")
    @classmethod
    def _supported(cls, code: str) -> str:
        languages.require(code)
        return code


def load_scenarios(path: Path = SCENARIOS_PATH) -> list[Scenario]:
    return [Scenario.model_validate(raw) for raw in json.loads(path.read_text(encoding="utf-8"))]
