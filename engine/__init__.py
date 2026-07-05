"""RIE engine — the RAF Integrity Engine, as a modular package.

Public surface mirrors the single-file spec (spec/rie_engine.py). `process_claim` is the brain;
the dataclasses and enums are the algorithm's vocabulary. Conformance tests assert this package
reproduces the spec byte-for-byte.
"""
from __future__ import annotations

from .accidents import match_score, normalise_cas, resolve_accident
from .adjudication import adjudicate_line, find_authorisation
from .corroboration import convergence, corroboration_signals
from .disposition import disposition
from .gates import merits_gate, prescription_gates, s24_gates, standing_gates
from .heads import (
    apportion, head_general_damages, head_loss_of_earnings, head_past_medical,
)
from .models import (
    Accident, Assessment, Authorisation, Claim, Line, LineResult, Ruleset, Undertaking,
)
from .payments import eligible_to_pay
from .pipeline import process_claim
from .reasons import MODE, R
from .reference import RefBook, dispensing_fee, resolve
from .scoring import score_and_band
from .vocab import (
    AMBER_AT, Band, Category, ENDOGENOUS_POINT_CAP, LegalStatus, Maturity, PAYMENT_RULE_STATUSES,
    RED_AT, ReasonMeta, SignalMode,
)

__all__ = [
    "process_claim", "score_and_band", "disposition", "eligible_to_pay",
    "resolve", "dispensing_fee", "RefBook", "adjudicate_line", "find_authorisation",
    "resolve_accident", "normalise_cas", "match_score", "convergence", "corroboration_signals",
    "prescription_gates", "s24_gates", "standing_gates", "merits_gate",
    "apportion", "head_past_medical", "head_loss_of_earnings", "head_general_damages",
    "Claim", "Line", "Accident", "Authorisation", "Undertaking", "Ruleset", "LineResult",
    "Assessment", "R", "MODE",
    "LegalStatus", "Maturity", "SignalMode", "Category", "Band", "ReasonMeta",
    "PAYMENT_RULE_STATUSES", "AMBER_AT", "RED_AT", "ENDOGENOUS_POINT_CAP",
]
