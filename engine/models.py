"""Data shapes — the algorithm's view of the world (domain-logic §2).

Minimal dataclasses. `Ruleset` carries the effective-dated scheme rules; `Claim` is a tree
(claim -> lines), anchored to an `Accident`. `LineResult`/`Assessment` are engine outputs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from .vocab import Band


@dataclass
class Ruleset:                     # effective at accident date (§1)
    lodgement_years_identified: int = 3
    lodgement_years_hitrun: int = 2
    summons_years: int = 5
    investigation_days: int = 120
    wpi_threshold: float = 30.0
    caps: list[tuple[date, float]] = field(default_factory=list)   # (effective_from, annual_cap)
    preauth_required: set[str] = field(default_factory=set)        # code classes needing pre-auth
    s19_grounds: set[str] = field(default_factory=set)

    def cap_at(self, accident_date: date) -> float:                # §5c — Sweatman/s17(4A)(b)
        rows = [c for eff, c in sorted(self.caps) if eff <= accident_date]
        return rows[-1] if rows else 0.0


@dataclass
class Line:
    kind: str                      # 'TARIFF' | 'NAPPI'
    code: str
    qty: float
    amount: float                  # billed, rand
    service_date: date
    provider_id: str
    dx: str                        # ICD-10 on the line
    emergency: bool = False
    scheme_paid: bool = False
    discipline: str = ""           # billing provider's discipline; "" -> claim default (§3)


@dataclass
class Authorisation:               # §5f — a promise priced in advance
    codes: set[str]
    qty_limit: float
    ceiling: float                 # rand
    valid_from: date
    valid_to: date
    status: str = "APPROVED"


@dataclass
class Undertaking:                 # §8c
    active: bool
    scope_dx: set[str]             # ICD-10 set (3-char compared)
    scope_coded: bool
    authorisations: list[Authorisation] = field(default_factory=list)


@dataclass
class Claim:
    claim_id: str
    claim_type: str                # PERSONAL | SUPPLIER | UNDERTAKING_INVOICE
    party_token: str
    accident_date: date
    lodged_on: date
    case_number_raw: Optional[str]
    documents: dict[str, bool]     # s24 checklist (§4b)
    lines: list[Line]
    heads: dict[str, dict] = field(default_factory=dict)   # head -> inputs
    hit_and_run: bool = False
    prescription_suspended: bool = False
    fault_pct: Optional[float] = None       # merits determination, 0..100
    merits_accepted: Optional[bool] = None
    merits_ground: Optional[str] = None
    si_accepted: Optional[bool] = None      # RAF 4 outcome (§8b)
    undertaking: Optional[Undertaking] = None
    claimant_deceased_on: Optional[date] = None
    payee_verified: bool = False
    attorney_in_standing: bool = True
    provider_registered: bool = True


@dataclass
class Accident:                    # §6.0
    accident_id: str
    case_number: Optional[str]
    when: date
    where: str
    vehicles: set[str]
    parties: set[str]
    oar_occupants: Optional[int]
    sources: dict[str, str] = field(default_factory=dict)  # source_class -> cluster_id
    claims: list[str] = field(default_factory=list)


@dataclass
class LineResult:
    payable: float
    reasons: list[str]
    src: str
    needs_review: bool = False


@dataclass
class Assessment:
    reasons: list[str]             # SCORED + ADVISORY (visible)
    shadow: list[str]              # computed, invisible
    score: int
    band: Band
    engine_version: str = "rie-scorer v1"
