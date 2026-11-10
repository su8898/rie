"""The reason-code catalogue R and the live signal MODE map (domain-logic §10, §11).

Every code ships with maturity + basis + citation — defensibility is not a retrofit.
"""
from __future__ import annotations

from .vocab import Category, Maturity, ReasonMeta, SignalMode

R: dict[str, ReasonMeta] = {
    # HARD gates — Grounded
    "PRESCRIBED_LODGEMENT":    ReasonMeta(Category.COMPLIANCE, True, 0, Maturity.GROUNDED, basis="s23"),
    "PRESCRIBED_SUMMONS":      ReasonMeta(Category.COMPLIANCE, True, 0, Maturity.GROUNDED, basis="s23(3)"),
    "S24_INCOMPLETE":          ReasonMeta(Category.COMPLIANCE, True, 0, Maturity.GROUNDED, basis="s24"),
    "OAR_MISSING":             ReasonMeta(Category.COMPLIANCE, True, 0, Maturity.GROUNDED, basis="s24 + reg"),
    "DUPLICATE_CLAIM":         ReasonMeta(Category.COMPLIANCE, True, 0, Maturity.GROUNDED, basis="one claim per claimant per accident"),
    "PROVIDER_UNREGISTERED":   ReasonMeta(Category.COMPLIANCE, True, 0, Maturity.GROUNDED, basis="HPCSA/BHF register"),
    "ATTORNEY_NOT_IN_STANDING":ReasonMeta(Category.COMPLIANCE, True, 0, Maturity.GROUNDED, basis="LPC register (payment hold)"),
    "PAYEE_UNVERIFIED":        ReasonMeta(Category.COMPLIANCE, True, 0, Maturity.GROUNDED, basis="AVS"),
    "LIFE_STATUS_MISMATCH":    ReasonMeta(Category.COMPLIANCE, True, 0, Maturity.GROUNDED, basis="DHA / death certificate (§5g)"),
    "SOLE_NEGLIGENCE":         ReasonMeta(Category.MERITS,     True, 0, Maturity.GROUNDED, basis="s17(1)"),
    "S19_EXCLUSION":           ReasonMeta(Category.MERITS,     True, 0, Maturity.GROUNDED, basis="s19"),
    "NO_MVA_NEXUS":            ReasonMeta(Category.MERITS,     True, 0, Maturity.GROUNDED, basis="s17(1) driving nexus"),
    "SERVICE_BEFORE_ACCIDENT": ReasonMeta(Category.COMPLIANCE, True, 0, Maturity.GROUNDED, basis="date CHECK"),
    "SUPPLIER_PRECLUSION":     ReasonMeta(Category.ADJUSTED,   True, 0, Maturity.GROUNDED, basis="s17(5) — pay once"),
    "DUPLICATE_LINE":          ReasonMeta(Category.ADJUSTED,   True, 0, Maturity.GROUNDED, basis="pay first occurrence"),
    "PREAUTH_MISSING":         ReasonMeta(Category.PREAUTH,    True, 0, Maturity.GROUNDED, basis="§5f ruleset"),
    "PREAUTH_EXCEEDED":        ReasonMeta(Category.ADJUSTED,   True, 0, Maturity.GROUNDED, basis="§5f — reprice to ceiling"),
    "UNDERTAKING_NOT_ACTIVE":  ReasonMeta(Category.COMPLIANCE, True, 0, Maturity.GROUNDED, basis="s17(4)(a)"),
    "UNDERTAKING_SCOPE":       ReasonMeta(Category.COMPLIANCE, True, 0, Maturity.GROUNDED, basis="undertaking terms (soft if uncoded)"),
    "GENERAL_DAMAGES_NO_SI":   ReasonMeta(Category.SI_GATE,    True, 0, Maturity.GROUNDED, basis="reg 3 / RAF 4"),
    "EARNINGS_UNPROVEN":       ReasonMeta(Category.COMPLIANCE, True, 0, Maturity.GROUNDED, basis="proof requirement"),
    "REFERENCE_UNRESOLVED":    ReasonMeta(Category.REVIEW,     True, 0, Maturity.GROUNDED, basis="§3 — no benchmark for the code; R&N review before payment"),
    # Soft features
    "BILLED_OVER_REFERENCE":   ReasonMeta(Category.ADJUSTED,   False,  0, Maturity.GROUNDED, basis="repriced when enforceable/accepted; else signal"),
    "VALUE_OUTLIER":           ReasonMeta(Category.FRAUD, False, 15, Maturity.HEURISTIC, endogenous=True, basis="condition band p90"),
    "VALUE_OUTLIER_EXTREME":   ReasonMeta(Category.FRAUD, False, 30, Maturity.HEURISTIC, endogenous=True, basis="condition band, extreme"),
    "LINE_COUNT_OUTLIER":      ReasonMeta(Category.FRAUD, False, 15, Maturity.HEURISTIC, endogenous=True, basis="corpus percentile"),
    "MATERIAL_PADDING":        ReasonMeta(Category.FRAUD, False, 15, Maturity.HEURISTIC, basis="NAPPI-dominated encounter"),
    "IMPOSSIBLE_DAY":          ReasonMeta(Category.FRAUD, False, 25, Maturity.HEURISTIC, basis="billed minutes > plausible day"),
    "DX_ACCIDENT_MISMATCH":    ReasonMeta(Category.FRAUD, False, 15, Maturity.HEURISTIC, basis="body region vs accident profile"),
    "PRE_EXISTING_CONDITION":  ReasonMeta(Category.COMPLIANCE, False, 5, Maturity.HEURISTIC, basis="review — aggravation compensable"),
    "INJURY_ESCALATION":       ReasonMeta(Category.FRAUD, False, 15, Maturity.HEURISTIC, basis="RAF1/4 vs first-contact records"),
    "OAR_MISMATCH":            ReasonMeta(Category.FRAUD, False,  5, Maturity.HEURISTIC, basis="SAPS data quality (LOW, never sole ground)"),
    "OAR_REUSED":              ReasonMeta(Category.FRAUD, False, 15, Maturity.HEURISTIC, basis="conflicting accident records, one CAS"),
    "EARNINGS_OUTLIER":        ReasonMeta(Category.FRAUD, False, 10, Maturity.HEURISTIC, endogenous=True, basis="sector band"),
    "LATE_CLAIM_CLUSTER":      ReasonMeta(Category.FRAUD, False, 15, Maturity.HEURISTIC, basis="deadline clustering"),
    # Graph / collusion — launch in SHADOW (§11)
    "RING_PARTIES":            ReasonMeta(Category.FRAUD, False, 25, Maturity.UNVALIDATED, basis="party-graph recurrence"),
    "CLAIMANT_SURGE":          ReasonMeta(Category.FRAUD, False, 20, Maturity.UNVALIDATED, basis="claimants vs capacity, cohort-aware"),
    "CLAIMANT_RECURRENCE":     ReasonMeta(Category.FRAUD, False, 15, Maturity.UNVALIDATED, basis="P_* across accidents"),
    "CONVERGENCE_THIN":        ReasonMeta(Category.FRAUD, False, 20, Maturity.UNVALIDATED, basis="evidence density/timing (§6.0)"),
}

# Live signal modes — reference data, not code (§11). Defaults at launch:
MODE: dict[str, SignalMode] = {
    code: (SignalMode.SHADOW if meta.maturity is Maturity.UNVALIDATED else SignalMode.SCORED)
    for code, meta in R.items()
}
