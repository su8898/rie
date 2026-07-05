"""Per-function unit tests for engine.disposition — concrete value assertions.

Worst-wins over Category enum order: FRAUD(1) > MERITS(2) > COMPLIANCE(3) > PREAUTH(4)
> SI_GATE(5) > ADJUSTED(6) > CLEAN(7). Only reasons present in R contribute a category.
"""
from __future__ import annotations

from engine.disposition import disposition
from engine.models import Assessment
from engine.vocab import Band, Category


def _asmt(reasons) -> Assessment:
    return Assessment(reasons=list(reasons), shadow=[], score=0, band=Band.GREEN)


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


def test_merits_pending_promotes_clean_to_merits():
    # only an adjusted reason present, but merits_pending injects MERITS which is worse
    assert disposition(_asmt(["BILLED_OVER_REFERENCE"]), merits_pending=True) is Category.MERITS
