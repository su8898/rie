"""Per-function unit tests for engine.disposition — concrete value assertions.

Worst-wins over Category enum order: FRAUD(1) > MERITS(2) > COMPLIANCE(3) > PREAUTH(4)
> SI_GATE(5) > REVIEW(6) > ADJUSTED(7) > CLEAN(8). Only dispositive reasons present in R
contribute a category (H5): hard gates and zero-point facts always, scoring heuristics only
at AMBER or above, ADVISORY signals never.
"""
from __future__ import annotations

from engine.disposition import disposition
from engine.models import Assessment
from engine.vocab import Band, Category


def _asmt(reasons, band=Band.AMBER, advisory=()) -> Assessment:
    # default band AMBER: soft heuristics only route once the band says "look" (H5)
    return Assessment(reasons=list(reasons), shadow=[], score=0, band=band, advisory=list(advisory))


def test_empty_reasons_is_clean():
    assert disposition(_asmt([]), merits_pending=False) is Category.CLEAN


def test_merits_pending_injects_merits():
    assert disposition(_asmt([]), merits_pending=True) is Category.MERITS


def test_single_fraud_category():
    # VALUE_OUTLIER is FRAUD
    assert disposition(_asmt(["VALUE_OUTLIER"]), False) is Category.FRAUD


def test_single_merits_category():
    assert disposition(_asmt(["S19_EXCLUSION"]), False) is Category.MERITS


def test_single_compliance_category():
    assert disposition(_asmt(["PRESCRIBED_LODGEMENT"]), False) is Category.COMPLIANCE


def test_single_preauth_category():
    assert disposition(_asmt(["PREAUTH_MISSING"]), False) is Category.PREAUTH


def test_single_si_gate_category():
    assert disposition(_asmt(["GENERAL_DAMAGES_NO_SI"]), False) is Category.SI_GATE


def test_single_adjusted_category():
    assert disposition(_asmt(["BILLED_OVER_REFERENCE"]), False) is Category.ADJUSTED


def test_fraud_beats_merits():
    assert disposition(_asmt(["S19_EXCLUSION", "VALUE_OUTLIER"]), False) is Category.FRAUD


def test_merits_beats_compliance_and_preauth():
    assert disposition(_asmt(["PREAUTH_MISSING", "PRESCRIBED_LODGEMENT", "S19_EXCLUSION"]), False) \
        is Category.MERITS


def test_compliance_beats_preauth():
    assert disposition(_asmt(["PREAUTH_MISSING", "OAR_MISSING"]), False) is Category.COMPLIANCE


def test_preauth_beats_si_gate_and_adjusted():
    assert disposition(_asmt(["BILLED_OVER_REFERENCE", "GENERAL_DAMAGES_NO_SI", "PREAUTH_MISSING"]), False) \
        is Category.PREAUTH


def test_si_gate_beats_adjusted():
    assert disposition(_asmt(["BILLED_OVER_REFERENCE", "GENERAL_DAMAGES_NO_SI"]), False) \
        is Category.SI_GATE


def test_merits_pending_injects_but_fraud_still_wins():
    # merits_pending adds MERITS(2), but FRAUD(1) is worse
    assert disposition(_asmt(["VALUE_OUTLIER"]), merits_pending=True) is Category.FRAUD


def test_unknown_codes_ignored():
    # codes not in R contribute no category -> CLEAN
    assert disposition(_asmt(["NOT_A_REAL_CODE"]), False) is Category.CLEAN


# ── H5: heuristics route only through the band; ADVISORY never routes ────────
def test_single_green_heuristic_does_not_dispose():
    # a 15-point DX mismatch alone: GREEN band -> informational, the claim stays CLEAN
    assert disposition(_asmt(["DX_ACCIDENT_MISMATCH"], band=Band.GREEN), False) is Category.CLEAN


def test_green_heuristics_dispose_once_band_is_amber():
    assert disposition(_asmt(["DX_ACCIDENT_MISMATCH"], band=Band.AMBER), False) is Category.FRAUD
    assert disposition(_asmt(["DX_ACCIDENT_MISMATCH"], band=Band.RED), False) is Category.FRAUD


def test_hard_gate_disposes_regardless_of_band():
    assert disposition(_asmt(["PRESCRIBED_LODGEMENT"], band=Band.GREEN), False) is Category.COMPLIANCE


def test_zero_point_fact_disposes_regardless_of_band():
    # BILLED_OVER_REFERENCE is a repricing fact (0 points) -> ADJUSTED even on GREEN
    assert disposition(_asmt(["BILLED_OVER_REFERENCE"], band=Band.GREEN), False) is Category.ADJUSTED


def test_advisory_signal_never_disposes():
    a = _asmt(["DX_ACCIDENT_MISMATCH"], band=Band.RED, advisory=["DX_ACCIDENT_MISMATCH"])
    assert disposition(a, False) is Category.CLEAN


def test_reference_unresolved_routes_to_review_below_adjusted():
    assert disposition(_asmt(["BILLED_OVER_REFERENCE", "REFERENCE_UNRESOLVED"], band=Band.GREEN), False) \
        is Category.REVIEW
    assert disposition(_asmt(["GENERAL_DAMAGES_NO_SI", "REFERENCE_UNRESOLVED"]), False) is Category.SI_GATE


def test_merits_pending_promotes_clean_to_merits():
    # only an adjusted reason present, but merits_pending injects MERITS which is worse
    assert disposition(_asmt(["BILLED_OVER_REFERENCE"]), merits_pending=True) is Category.MERITS
