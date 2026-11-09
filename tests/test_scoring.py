"""Per-function unit tests for engine.scoring — concrete value assertions.

Point sources (from reasons.R, all SCORED at launch except UNVALIDATED->SHADOW):
  IMPOSSIBLE_DAY 25 (non-endo), MATERIAL_PADDING 15 (non-endo), DX_ACCIDENT_MISMATCH 15 (non-endo),
  VALUE_OUTLIER 15 (endo), VALUE_OUTLIER_EXTREME 30 (endo), LINE_COUNT_OUTLIER 15 (endo),
  EARNINGS_OUTLIER 10 (endo). Bands: GREEN < 25 <= AMBER < 50 <= RED. ENDOGENOUS_POINT_CAP 45.
Note: no catalogue code is BOTH hard AND FRAUD, so the +50 branch is tested via monkeypatch.
"""
from __future__ import annotations

import pytest

import engine.reasons as reasons
from engine.scoring import score_and_band
from engine.vocab import (
    AMBER_AT, Band, Category, ENDOGENOUS_POINT_CAP, Maturity, RED_AT, ReasonMeta, SignalMode,
)


# ── soft SCORED points sum & bands ───────────────────────────────────────────
def test_single_soft_below_amber_is_green():
    a = score_and_band(["VALUE_OUTLIER"])       # 15 endo -> capped 15 -> GREEN
    assert a.score == 15 and a.band is Band.GREEN
    assert a.reasons == ["VALUE_OUTLIER"] and a.shadow == []


def test_score_at_amber_threshold_is_amber():
    a = score_and_band(["IMPOSSIBLE_DAY"])      # 25 non-endo -> AMBER (25 >= 25)
    assert a.score == 25 and a.band is Band.AMBER


def test_soft_points_sum_across_codes():
    # MATERIAL_PADDING 15 + IMPOSSIBLE_DAY 25 = 40 -> AMBER
    a = score_and_band(["MATERIAL_PADDING", "IMPOSSIBLE_DAY"])
    assert a.score == 40 and a.band is Band.AMBER


def test_soft_points_reach_red():
    # MATERIAL_PADDING 15 + IMPOSSIBLE_DAY 25 + DX_ACCIDENT_MISMATCH 15 = 55 -> RED
    a = score_and_band(["MATERIAL_PADDING", "IMPOSSIBLE_DAY", "DX_ACCIDENT_MISMATCH"])
    assert a.score == 55 and a.band is Band.RED


def test_below_amber_stays_green():
    # PRE_EXISTING_CONDITION 5 + OAR_MISMATCH 5 = 10 -> GREEN
    a = score_and_band(["PRE_EXISTING_CONDITION", "OAR_MISMATCH"])
    assert a.score == 10 and a.band is Band.GREEN


# ── endogenous cap ───────────────────────────────────────────────────────────
def test_endogenous_points_capped_below_red():
    # 30 + 15 + 15 + 10 = 70 endo -> min(70, 45) = 45 -> AMBER, never RED
    a = score_and_band(["VALUE_OUTLIER_EXTREME", "VALUE_OUTLIER", "LINE_COUNT_OUTLIER", "EARNINGS_OUTLIER"])
    assert a.score == ENDOGENOUS_POINT_CAP == 45
    assert a.band is Band.AMBER


def test_endogenous_plus_non_endogenous_can_exceed_cap():
    # endo VALUE_OUTLIER 15 (capped at 15) + non-endo IMPOSSIBLE_DAY 25 + non-endo DX 15 = 55 -> RED
    a = score_and_band(["VALUE_OUTLIER", "IMPOSSIBLE_DAY", "DX_ACCIDENT_MISMATCH"])
    assert a.score == 55 and a.band is Band.RED


def test_endogenous_only_two_codes_within_cap():
    # 15 + 15 = 30 endo -> not capped -> AMBER
    a = score_and_band(["VALUE_OUTLIER", "LINE_COUNT_OUTLIER"])
    assert a.score == 30 and a.band is Band.AMBER


# ── SHADOW mode ──────────────────────────────────────────────────────────────
def test_shadow_reason_zero_points_goes_to_shadow_list():
    # RING_PARTIES is UNVALIDATED -> SHADOW -> zero points, invisible
    a = score_and_band(["RING_PARTIES"])
    assert a.reasons == [] and a.shadow == ["RING_PARTIES"]
    assert a.score == 0 and a.band is Band.GREEN


def test_shadow_does_not_contribute_even_with_visible_reasons():
    a = score_and_band(["IMPOSSIBLE_DAY", "CONVERGENCE_THIN"])  # CONVERGENCE_THIN is SHADOW
    assert a.reasons == ["IMPOSSIBLE_DAY"]
    assert a.shadow == ["CONVERGENCE_THIN"]
    assert a.score == 25


# ── unknown codes stay visible with no points ────────────────────────────────
def test_unknown_code_kept_visible_no_points():
    a = score_and_band(["TOTALLY_UNKNOWN"])
    assert a.reasons == ["TOTALLY_UNKNOWN"] and a.shadow == []
    assert a.score == 0 and a.band is Band.GREEN


def test_hard_gate_reason_visible_no_points():
    # PRESCRIBED_LODGEMENT is hard, COMPLIANCE (not FRAUD), 0 points -> visible, no score
    a = score_and_band(["PRESCRIBED_LODGEMENT"])
    assert a.reasons == ["PRESCRIBED_LODGEMENT"]
    assert a.score == 0 and a.band is Band.GREEN


# ── dedupe keeps order ───────────────────────────────────────────────────────
def test_dedupe_keeps_first_order_and_counts_once():
    a = score_and_band(["IMPOSSIBLE_DAY", "MATERIAL_PADDING", "IMPOSSIBLE_DAY"])
    assert a.reasons == ["IMPOSSIBLE_DAY", "MATERIAL_PADDING"]  # order preserved, deduped
    assert a.score == 40  # counted once each (25 + 15)


# ── hard FRAUD +50 branch (monkeypatched: no catalogue code is hard+FRAUD) ────
def test_hard_fraud_reason_adds_50_and_bands_red(monkeypatch):
    monkeypatch.setitem(reasons.R, "TEST_HARD_FRAUD",
                        ReasonMeta(Category.FRAUD, True, 0, Maturity.GROUNDED))
    monkeypatch.setitem(reasons.MODE, "TEST_HARD_FRAUD", SignalMode.SCORED)
    a = score_and_band(["TEST_HARD_FRAUD"])
    assert a.score == 50 and a.band is Band.RED
    assert a.reasons == ["TEST_HARD_FRAUD"]


def test_band_thresholds_constants():
    assert (AMBER_AT, RED_AT) == (25, 50)


# ── H5 / H8: ADVISORY tracked, Grounded never overridable, bogus overrides ignored ──
def test_advisory_override_is_visible_zero_points_and_listed():
    a = score_and_band(["DX_ACCIDENT_MISMATCH"], {"DX_ACCIDENT_MISMATCH": SignalMode.ADVISORY})
    assert a.reasons == ["DX_ACCIDENT_MISMATCH"] and a.advisory == ["DX_ACCIDENT_MISMATCH"]
    assert a.score == 0 and a.band is Band.GREEN


def test_grounded_gate_cannot_be_shadowed_or_made_advisory():
    for mode in (SignalMode.SHADOW, SignalMode.ADVISORY):
        a = score_and_band(["PRESCRIBED_LODGEMENT"], {"PRESCRIBED_LODGEMENT": mode})
        assert a.reasons == ["PRESCRIBED_LODGEMENT"] and a.shadow == [] and a.advisory == []


def test_non_enum_override_value_is_ignored():
    a = score_and_band(["DX_ACCIDENT_MISMATCH"], {"DX_ACCIDENT_MISMATCH": "SHADOW"})
    assert a.reasons == ["DX_ACCIDENT_MISMATCH"] and a.score == 15 and a.advisory == []


def test_effective_mode_without_meta_falls_back_to_default():
    from engine.scoring import effective_mode
    assert effective_mode("NOT_A_CODE", None, {"NOT_A_CODE": SignalMode.SHADOW}) is SignalMode.SCORED
    assert effective_mode("RING_PARTIES", reasons.R["RING_PARTIES"], {}) is SignalMode.SHADOW
    assert effective_mode("RING_PARTIES", reasons.R["RING_PARTIES"],
                          {"RING_PARTIES": SignalMode.SCORED}) is SignalMode.SCORED
