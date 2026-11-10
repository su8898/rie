"""RIE engine — the RAF Integrity Engine, as a modular package.

Public surface mirrors the single-file spec (spec/rie_engine.py). `process_claim` is the brain;
the dataclasses and enums are the algorithm's vocabulary. Conformance tests assert this package
reproduces the spec byte-for-byte.
"""
from __future__ import annotations

from .accidents import match_score, normalise_cas, resolve_accident
from .adjudication import adjudicate_line, consume_authorisation, find_authorisation, line_key
from .coding import (
    ANAES_TIME_RULES, CODE_RULES, ONCE_PER_ENCOUNTER, PCT_OF_TIME, TIME_ANAES, TIME_BLOCK,
    TIME_FIRST_HOUR, TIME_RULES, blocks, code_rule, encounter_key, line_reference, time_total,
)
from .corroboration import convergence, corroboration_signals
from .disposition import disposition, dispositive
from .gates import add_years, merits_gate, prescription_gates, s24_gates, standing_gates
from .heads import (
    apportion, head_funeral, head_general_damages, head_loss_of_earnings,
    head_loss_of_support, head_past_medical,
)
from .models import (
    Accident, Activity, Assessment, Authorisation, Claim, Line, LineResult, Ruleset,
    Undertaking, normalise_code,
)
from .payments import eligible_to_pay
from .pipeline import process_claim
from .reasons import LAUNCH_ADVISORY, MODE, R
from .reference import RefBook, dispensing_fee, rate_on, resolve
from .scoring import effective_mode, score_and_band
from .signals import billing_signals, iso_week, padded
from .vocab import (
    AMBER_AT, Band, Category, D, ENDOGENOUS_POINT_CAP, LegalStatus, Maturity,
    PAYMENT_RULE_STATUSES, RED_AT, ReasonMeta, SignalMode, money,
)

__all__ = [
    "process_claim", "score_and_band", "effective_mode", "disposition", "dispositive",
    "eligible_to_pay", "resolve", "rate_on", "dispensing_fee", "RefBook", "normalise_code",
    "adjudicate_line", "find_authorisation", "line_key", "consume_authorisation",
    "resolve_accident", "normalise_cas", "match_score", "convergence", "corroboration_signals",
    "prescription_gates", "add_years", "s24_gates", "standing_gates", "merits_gate",
    "apportion", "head_past_medical", "head_loss_of_earnings", "head_loss_of_support",
    "head_general_damages", "head_funeral",
    "code_rule", "encounter_key", "blocks", "time_total", "line_reference",
    "ONCE_PER_ENCOUNTER", "TIME_BLOCK", "TIME_ANAES", "TIME_FIRST_HOUR", "PCT_OF_TIME",
    "TIME_RULES", "ANAES_TIME_RULES", "CODE_RULES",
    "billing_signals", "iso_week", "padded",
    "Claim", "Line", "Accident", "Activity", "Authorisation", "Undertaking", "Ruleset",
    "LineResult", "Assessment", "R", "MODE", "LAUNCH_ADVISORY",
    "LegalStatus", "Maturity", "SignalMode", "Category", "Band", "ReasonMeta",
    "PAYMENT_RULE_STATUSES", "AMBER_AT", "RED_AT", "ENDOGENOUS_POINT_CAP", "D", "money",
]
