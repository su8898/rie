"""Per-function unit tests for engine.reasons — catalogue R and MODE sanity.

Invariants: every UNVALIDATED reason maps to SHADOW in MODE; every GROUNDED/HEURISTIC reason
maps to SCORED. Plus concrete category/points/hard/maturity for representative codes.
"""
from __future__ import annotations

from engine.reasons import MODE, R
from engine.vocab import Category, Maturity, SignalMode


# ── MODE derivation invariant ────────────────────────────────────────────────
def test_every_reason_has_a_mode():
    assert set(MODE) == set(R)


def test_unvalidated_maps_to_shadow_others_to_scored():
    for code, meta in R.items():
        expected = SignalMode.SHADOW if meta.maturity is Maturity.UNVALIDATED else SignalMode.SCORED
        assert MODE[code] is expected, (code, MODE[code])


def test_unvalidated_codes_are_exactly_the_graph_signals():
    unvalidated = {c for c, m in R.items() if m.maturity is Maturity.UNVALIDATED}
    assert unvalidated == {"RING_PARTIES", "CLAIMANT_SURGE", "CLAIMANT_RECURRENCE", "CONVERGENCE_THIN"}


def test_all_shadow_modes_are_unvalidated():
    shadow = {c for c, m in MODE.items() if m is SignalMode.SHADOW}
    assert shadow == {"RING_PARTIES", "CLAIMANT_SURGE", "CLAIMANT_RECURRENCE", "CONVERGENCE_THIN"}


# ── representative hard grounded gates ───────────────────────────────────────
def test_prescribed_lodgement_meta():
    m = R["PRESCRIBED_LODGEMENT"]
    assert m.category is Category.COMPLIANCE and m.hard is True
    assert m.points == 0 and m.maturity is Maturity.GROUNDED


def test_s19_exclusion_is_hard_merits():
    m = R["S19_EXCLUSION"]
    assert m.category is Category.MERITS and m.hard is True and m.maturity is Maturity.GROUNDED


def test_service_before_accident_is_compliance_hard():
    m = R["SERVICE_BEFORE_ACCIDENT"]
    assert m.category is Category.COMPLIANCE and m.hard is True


def test_preauth_missing_is_preauth_category():
    assert R["PREAUTH_MISSING"].category is Category.PREAUTH and R["PREAUTH_MISSING"].hard is True


def test_preauth_exceeded_is_adjusted():
    assert R["PREAUTH_EXCEEDED"].category is Category.ADJUSTED


def test_general_damages_no_si_is_si_gate():
    assert R["GENERAL_DAMAGES_NO_SI"].category is Category.SI_GATE and R["GENERAL_DAMAGES_NO_SI"].hard is True


def test_duplicate_line_is_adjusted_hard():
    assert R["DUPLICATE_LINE"].category is Category.ADJUSTED and R["DUPLICATE_LINE"].hard is True


# ── representative soft heuristic features ───────────────────────────────────
def test_billed_over_reference_soft_zero_points():
    m = R["BILLED_OVER_REFERENCE"]
    assert m.category is Category.ADJUSTED and m.hard is False and m.points == 0


def test_value_outlier_soft_endogenous_15():
    m = R["VALUE_OUTLIER"]
    assert m.category is Category.FRAUD and m.hard is False
    assert m.points == 15 and m.endogenous is True and m.maturity is Maturity.HEURISTIC


def test_value_outlier_extreme_endogenous_30():
    m = R["VALUE_OUTLIER_EXTREME"]
    assert m.points == 30 and m.endogenous is True and m.category is Category.FRAUD


def test_impossible_day_non_endogenous_25():
    m = R["IMPOSSIBLE_DAY"]
    assert m.points == 25 and m.endogenous is False and m.category is Category.FRAUD


def test_earnings_outlier_endogenous_10():
    m = R["EARNINGS_OUTLIER"]
    assert m.points == 10 and m.endogenous is True


# ── graph / collusion shadow codes ───────────────────────────────────────────
def test_ring_parties_unvalidated_shadow():
    m = R["RING_PARTIES"]
    assert m.category is Category.FRAUD and m.points == 25 and m.maturity is Maturity.UNVALIDATED
    assert MODE["RING_PARTIES"] is SignalMode.SHADOW


def test_convergence_thin_unvalidated_shadow():
    assert R["CONVERGENCE_THIN"].maturity is Maturity.UNVALIDATED
    assert MODE["CONVERGENCE_THIN"] is SignalMode.SHADOW


# ── no catalogue code is both hard AND FRAUD (scoring +50 branch is dormant) ──
def test_no_hard_fraud_codes_in_catalogue():
    hard_fraud = [c for c, m in R.items() if m.hard and m.category is Category.FRAUD]
    assert hard_fraud == []


def test_catalogue_size():
    assert len(R) == 38
