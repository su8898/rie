"""Typed, bounded claim submission (the money path's input contract).

Every claim that reaches the engine — from the operator API or the provider rails — passes
through `validate_submission` AFTER pseudonymisation. It is a pydantic model with the bounds the
engine itself does not enforce: positive quantities, non-negative finite amounts, known line
kinds, boolean document flags (a string like "missing" is not a present document), fault in
0..100, a merits ground from the s19 register, and a party token that is a pseudonym rather than
a raw 13-digit identifier. Unknown keys are kept (payloads carry RCJ extras), but every declared
field is checked. Dates are returned as ISO strings so the adapter is unchanged.
"""
from __future__ import annotations

import math
import re
from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, StrictBool, ValidationError, field_validator, model_validator

from engine.reasons import R
from engine.vocab import Category

MERITS_GROUNDS = frozenset(code for code, meta in R.items() if meta.category == Category.MERITS)
_RAW_SA_ID = re.compile(r"^\d{13}$")
MAX_LINE_AMOUNT = 100_000_000.0            # R100m on one line is not a claim, it is a typo or an attack
MAX_QTY = 10_000.0


class SubmissionError(ValueError):
    """Structured validation failure -> HTTP 422 (operator) / RailsError 422 (rails)."""

    def __init__(self, errors: list[dict]):
        super().__init__("; ".join(f"{'.'.join(str(x) for x in e['loc'])}: {e['msg']}" for e in errors))
        self.errors = errors


class LineIn(BaseModel):
    model_config = ConfigDict(extra="allow")
    kind: Literal["TARIFF", "NAPPI"]
    code: str = Field(min_length=1, max_length=32)
    qty: float = Field(gt=0, le=MAX_QTY)
    amount: float = Field(ge=0, le=MAX_LINE_AMOUNT)
    service_date: date
    provider_id: str = Field(min_length=1, max_length=64)
    dx: str = Field(default="", max_length=16)
    discipline: str = Field(default="", max_length=64)
    emergency: StrictBool = False
    scheme_paid: StrictBool = False

    @field_validator("qty", "amount")
    @classmethod
    def _finite(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("must be a finite number")
        return v


class ClaimSubmission(BaseModel):
    model_config = ConfigDict(extra="allow")
    claim_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._\-]*$")
    claim_type: Literal["SUPPLIER", "PERSONAL"]
    party_token: str = Field(min_length=1, max_length=64)
    accident_date: date
    lodged_on: date
    today: Optional[date] = None
    case_number_raw: Optional[str] = Field(default=None, max_length=64)
    documents: dict[str, StrictBool] = Field(default_factory=dict)
    lines: list[LineIn] = Field(default_factory=list, max_length=500)
    payee_verified: StrictBool = False
    attorney_in_standing: StrictBool = True
    provider_registered: StrictBool = True
    facility: StrictBool = False
    hit_and_run: StrictBool = False
    prescription_suspended: StrictBool = False
    cohort_is_bus_taxi: StrictBool = False
    fault_pct: Optional[float] = Field(default=None, ge=0, le=100)
    merits_accepted: Optional[StrictBool] = None
    merits_ground: Optional[str] = None
    si_accepted: Optional[StrictBool] = None
    claimant_deceased_on: Optional[date] = None
    summons_served: Optional[date] = None
    accident_dx_regions: list[str] = Field(default_factory=list, max_length=50)
    provider_tier: str = Field(default="GP", max_length=32)
    conv_floor_p10: float = Field(default=20.0, ge=0, le=100)

    @field_validator("party_token")
    @classmethod
    def _pseudonymous(cls, v: str) -> str:
        if _RAW_SA_ID.match(v.strip()):
            raise ValueError("looks like a raw national ID — send it as national_id, it is pseudonymised at ingest")
        return v

    @field_validator("merits_ground")
    @classmethod
    def _known_ground(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in MERITS_GROUNDS:
            raise ValueError(f"must be one of {sorted(MERITS_GROUNDS)}")
        return v

    @model_validator(mode="after")
    def _dates(self) -> "ClaimSubmission":
        if self.lodged_on < self.accident_date:
            raise ValueError("lodged_on precedes accident_date")
        if self.claimant_deceased_on is not None and self.claimant_deceased_on < self.accident_date:
            raise ValueError("claimant_deceased_on precedes accident_date")
        return self


def validate_submission(payload: dict) -> dict:
    """Validate a (pseudonymised) claim payload; return the normalised dict (dates as ISO strings,
    unknown keys preserved) or raise SubmissionError."""
    try:
        model = ClaimSubmission.model_validate(payload)
    except ValidationError as e:
        raise SubmissionError([{"loc": list(err["loc"]), "msg": err["msg"]} for err in e.errors()])
    # Only what the caller supplied (plus extras) — defaults are the adapter's job, and the stored
    # record must not acquire fund-side keys (payee_verified, ...) the submitter never sent.
    return model.model_dump(mode="json", exclude_none=True, exclude_unset=True)
