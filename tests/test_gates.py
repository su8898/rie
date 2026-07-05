"""Per-function unit tests for engine.gates — concrete value assertions.

Windows use timedelta(days=365 * years): identified 3y, hit-and-run 2y, summons 5y (Ruleset
defaults). The comparison is strict '>' against accident_date/lodged_on + window.
"""
from __future__ import annotations

from datetime import date

import pytest

from engine.gates import (
    MANDATORY_DOCS, merits_gate, prescription_gates, s24_gates, standing_gates,
)
from engine.models import Claim, Ruleset


def _claim(**over) -> Claim:
    base = dict(
        claim_id="R_1", claim_type="PERSONAL", party_token="P_1",
        accident_date=date(2026, 2, 1), lodged_on=date(2026, 3, 1),
        case_number_raw=None,
        documents={"RAF1": True, "OAR": True, "ID": True, "BANK": True}, lines=[],
    )
    base.update(over)
    return Claim(**base)


RS = Ruleset()  # defaults: identified 3y, hitrun 2y, summons 5y
TODAY = date(2026, 7, 5)


# ── prescription_gates ───────────────────────────────────────────────────────
def test_prescription_clean_within_window():
    assert prescription_gates(_claim(), RS, TODAY, None) == []


def test_prescription_identified_lodged_beyond_three_years():
    # accident 2020-01-01, lodged 2024-01-01 > 2020-01-01 + 3*365d -> PRESCRIBED_LODGEMENT
    c = _claim(accident_date=date(2020, 1, 1), lodged_on=date(2024, 1, 1))
    assert prescription_gates(c, RS, TODAY, None) == ["PRESCRIBED_LODGEMENT"]


def test_prescription_identified_just_inside_three_years_ok():
    # 3*365 = 1095 days after 2020-01-01 is 2022-12-31; lodging on that day is NOT > window
    c = _claim(accident_date=date(2020, 1, 1), lodged_on=date(2022, 12, 31))
    assert prescription_gates(c, RS, TODAY, None) == []


def test_prescription_hit_and_run_uses_two_year_window():
    # hit-and-run: accident 2023-01-01, lodged 2025-08-01 > 2023-01-01 + 2*365d (2024-12-31)
    c = _claim(hit_and_run=True, accident_date=date(2023, 1, 1), lodged_on=date(2025, 8, 1))
    assert prescription_gates(c, RS, TODAY, None) == ["PRESCRIBED_LODGEMENT"]


def test_prescription_hit_and_run_within_two_years_ok():
    c = _claim(hit_and_run=True, accident_date=date(2024, 1, 1), lodged_on=date(2025, 6, 1))
    assert prescription_gates(c, RS, TODAY, None) == []


def test_prescription_suspended_suppresses_lodgement():
    c = _claim(prescription_suspended=True, accident_date=date(2020, 1, 1), lodged_on=date(2024, 1, 1))
    assert prescription_gates(c, RS, TODAY, None) == []


def test_prescription_summons_beyond_five_years():
    # lodged 2026-03-01; summons window 5*365d -> 2031-02-28; served 2031-04-01 > that
    assert prescription_gates(_claim(), RS, TODAY, date(2031, 4, 1)) == ["PRESCRIBED_SUMMONS"]


def test_prescription_summons_within_five_years_ok():
    assert prescription_gates(_claim(), RS, TODAY, date(2030, 1, 1)) == []


def test_prescription_summons_none_no_check():
    assert prescription_gates(_claim(), RS, TODAY, None) == []


def test_prescription_lodgement_and_summons_both():
    c = _claim(accident_date=date(2020, 1, 1), lodged_on=date(2024, 1, 1))
    # lodged 2024-01-01 + 5y = 2028-12-30; summons 2031-04-01 > that too
    out = prescription_gates(c, RS, TODAY, date(2031, 4, 1))
    assert out == ["PRESCRIBED_LODGEMENT", "PRESCRIBED_SUMMONS"]


# ── s24_gates ────────────────────────────────────────────────────────────────
def test_s24_personal_complete_no_gate():
    assert s24_gates(_claim()) == []


def test_s24_incomplete_for_missing_non_oar_doc():
    c = _claim(documents={"RAF1": False, "OAR": True, "ID": True, "BANK": True})
    assert s24_gates(c) == ["S24_INCOMPLETE"]


def test_s24_oar_missing_emitted_separately():
    c = _claim(documents={"RAF1": True, "OAR": False, "ID": True, "BANK": True})
    assert s24_gates(c) == ["OAR_MISSING"]


def test_s24_oar_and_other_missing_both_emitted_oar_first():
    c = _claim(documents={"RAF1": False, "OAR": False, "ID": True, "BANK": True})
    assert s24_gates(c) == ["OAR_MISSING", "S24_INCOMPLETE"]


def test_s24_missing_key_absent_counts_as_missing():
    # BANK simply absent from the dict -> treated as missing -> S24_INCOMPLETE
    c = _claim(documents={"RAF1": True, "OAR": True, "ID": True})
    assert s24_gates(c) == ["S24_INCOMPLETE"]


def test_s24_supplier_docs():
    c = _claim(claim_type="SUPPLIER",
               documents={"RAF2": True, "OAR": True, "INVOICES": True, "BANK": True})
    assert s24_gates(c) == []


def test_s24_undertaking_invoice_docs_no_oar_required():
    c = _claim(claim_type="UNDERTAKING_INVOICE", documents={"INVOICES": True, "BANK": True})
    assert s24_gates(c) == []


def test_mandatory_docs_shape():
    assert MANDATORY_DOCS["PERSONAL"] == {"RAF1", "OAR", "ID", "BANK"}
    assert MANDATORY_DOCS["SUPPLIER"] == {"RAF2", "OAR", "INVOICES", "BANK"}
    assert MANDATORY_DOCS["UNDERTAKING_INVOICE"] == {"INVOICES", "BANK"}


# ── standing_gates ───────────────────────────────────────────────────────────
def test_standing_clean():
    assert standing_gates(_claim(), deceased_before_service=False) == []


def test_standing_provider_unregistered():
    assert standing_gates(_claim(provider_registered=False), False) == ["PROVIDER_UNREGISTERED"]


def test_standing_attorney_not_in_standing():
    assert standing_gates(_claim(attorney_in_standing=False), False) == ["ATTORNEY_NOT_IN_STANDING"]


def test_standing_life_status_mismatch():
    assert standing_gates(_claim(), deceased_before_service=True) == ["LIFE_STATUS_MISMATCH"]


def test_standing_all_three_in_order():
    c = _claim(provider_registered=False, attorney_in_standing=False)
    assert standing_gates(c, True) == \
        ["PROVIDER_UNREGISTERED", "ATTORNEY_NOT_IN_STANDING", "LIFE_STATUS_MISMATCH"]


# ── merits_gate ──────────────────────────────────────────────────────────────
def test_merits_rejected_default_ground_is_s19():
    assert merits_gate(_claim(merits_accepted=False)) == ["S19_EXCLUSION"]


def test_merits_rejected_explicit_ground():
    assert merits_gate(_claim(merits_accepted=False, merits_ground="SOLE_NEGLIGENCE")) == \
        ["SOLE_NEGLIGENCE"]


def test_merits_rejected_nexus_ground():
    assert merits_gate(_claim(merits_accepted=False, merits_ground="NO_MVA_NEXUS")) == \
        ["NO_MVA_NEXUS"]


def test_merits_accepted_no_reason():
    assert merits_gate(_claim(merits_accepted=True)) == []


def test_merits_pending_no_reason():
    # None = pending -> not a reason here (handled as held_for_merits downstream)
    assert merits_gate(_claim(merits_accepted=None)) == []
