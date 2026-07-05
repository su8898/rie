"""Eligibility, liability & compliance gates — grounded, hard, cited (domain-logic §4).

All Grounded (statute cited), all HARD gates, all evaluated against the ruleset effective at
accident date.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from .models import Claim, Ruleset


def prescription_gates(c: Claim, rs: Ruleset, today: date, summons_served: Optional[date]) -> list[str]:
    out = []
    years = rs.lodgement_years_hitrun if c.hit_and_run else rs.lodgement_years_identified
    if not c.prescription_suspended and c.lodged_on > c.accident_date + timedelta(days=365 * years):
        out.append("PRESCRIBED_LODGEMENT")
    if summons_served and summons_served > c.lodged_on + timedelta(days=365 * rs.summons_years):
        out.append("PRESCRIBED_SUMMONS")
    return out


MANDATORY_DOCS = {   # §4b — per claim type (abridged)
    "PERSONAL":            {"RAF1", "OAR", "ID", "BANK"},
    "SUPPLIER":            {"RAF2", "OAR", "INVOICES", "BANK"},
    "UNDERTAKING_INVOICE": {"INVOICES", "BANK"},
}


def s24_gates(c: Claim) -> list[str]:
    missing = MANDATORY_DOCS[c.claim_type] - {k for k, v in c.documents.items() if v}
    out = []
    if "OAR" in missing:
        out.append("OAR_MISSING")                    # universal hard item; OAR_PENDING pre-validation
        missing.discard("OAR")
    if missing:
        out.append("S24_INCOMPLETE")
    return out


def standing_gates(c: Claim, deceased_before_service: bool) -> list[str]:
    out = []
    if not c.provider_registered:  out.append("PROVIDER_UNREGISTERED")
    if not c.attorney_in_standing: out.append("ATTORNEY_NOT_IN_STANDING")   # payment hold
    if deceased_before_service:    out.append("LIFE_STATUS_MISMATCH")       # §5g
    return out


def merits_gate(c: Claim) -> list[str]:
    if c.merits_accepted is False:
        return [c.merits_ground or "S19_EXCLUSION"]   # SOLE_NEGLIGENCE | S19_EXCLUSION | NO_MVA_NEXUS
    return []                                         # None = pending -> held_for_merits (not a reason)
