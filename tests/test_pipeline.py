"""Per-function unit tests for engine.pipeline.process_claim — concrete determination records.

The RefBook is keyed on NORMALISED tariff codes ('190' for line code '0190') because resolve()
strips leading zeros; preauth_required keys on the raw line code. Expected values are computed
by hand from the module logic.
"""
from __future__ import annotations

from datetime import date

from engine.models import Accident, Claim, Line, Ruleset
from engine.pipeline import process_claim
from engine.reference import RefBook
from engine.vocab import SignalMode

TODAY = date(2026, 7, 5)


def _book(**over) -> RefBook:
    base = dict(
        negotiated={("TARIFF", "55"): 400.0},
        rpl={"190": {"GP": 500.0, "SPECIALIST": 700.0}},
        raf2022={"200": 300.0, "300": 50.0},
        empirical={("TARIFF", "300"): 300.0},
        sep={"700101": 88.40}, non_benchmarkable=set(),
    )
    base.update(over)
    return RefBook(**base)


def _rs(**over) -> Ruleset:
    base = dict(caps=[(date(2015, 1, 1), 160000.0), (date(2026, 1, 31), 378581.0)],
                preauth_required={"0500"})
    base.update(over)
    return Ruleset(**base)


def _line(**over) -> Line:
    base = dict(kind="TARIFF", code="0190", qty=1.0, amount=500.0,
                service_date=date(2026, 3, 1), provider_id="PR1", dx="S72")
    base.update(over)
    return Line(**base)


def _supplier(**over) -> Claim:
    base = dict(claim_id="R_1", claim_type="SUPPLIER", party_token="P_1",
                accident_date=date(2026, 2, 1), lodged_on=date(2026, 3, 1),
                case_number_raw="CAS 100/02/2026",
                documents={"RAF2": True, "OAR": True, "INVOICES": True, "BANK": True},
                lines=[_line()], payee_verified=True,
                attorney_in_standing=True, provider_registered=True)
    base.update(over)
    return Claim(**base)


def _personal(**over) -> Claim:
    base = dict(claim_id="R_2", claim_type="PERSONAL", party_token="P_1",
                accident_date=date(2026, 2, 1), lodged_on=date(2026, 3, 1),
                case_number_raw="CAS 100/02/2026",
                documents={"RAF1": True, "OAR": True, "ID": True, "BANK": True},
                lines=[_line()], payee_verified=True,
                attorney_in_standing=True, provider_registered=True)
    base.update(over)
    return Claim(**base)


# ── clean supplier claim ─────────────────────────────────────────────────────
def test_clean_supplier_full_record():
    d = process_claim(_supplier(), [], _book(), _rs(), TODAY)
    assert d["claim_id"] == "R_1"
    assert d["accident_id"] == "A_R_1"        # no accident passed -> minted from the claim id (H7)
    assert d["accident_action"] == "CREATED"
    assert d["band"] == "GREEN"
    assert d["score"] == 0
    assert d["disposition"] == "CLEAN"
    assert d["reasons"] == []
    # a freshly-minted accident has 0 convergence < default floor 20 -> a SHADOW-only
    # CONVERGENCE_THIN signal (zero points, invisible to band/disposition/eligibility)
    assert d["shadow_signals"] == ["CONVERGENCE_THIN"]
    assert d["medical_payable"] == 500.0       # rpl 500, billed 500, no fault
    assert d["eligible_to_pay"] is True
    assert d["net_payable"] == 500.0
    assert d["holds"] == []
    assert d["validated"] is True
    assert d["convergence"] == 0.0             # freshly created accident, no sources
    assert d["engine_version"] == "rie-scorer v1"
    assert d["ruleset_effective"] == "2026-02-01"
    assert d["reference_edition"] == "RPL-2026"


def test_clean_supplier_joins_existing_accident_by_cas():
    acc = Accident(accident_id="A_pre", case_number="CAS100/02/2026", when=date(2026, 2, 1),
                   where="", vehicles=set(), parties={"P_1"}, oar_occupants=5,
                   sources={"EMS": "c1", "HOSPITAL": "c2", "SAPS": "c3"})
    d = process_claim(_supplier(), [acc], _book(), _rs(), TODAY)
    assert d["accident_action"] == "JOINED"
    assert d["accident_id"] == "A_pre"
    assert d["convergence"] == 37.5            # EMS+HOSPITAL+SAPS = 4.5/12*100
    assert "R_1" in acc.claims               # side effect: claim id appended


# ── merits-pending personal claim ────────────────────────────────────────────
def test_merits_pending_personal_held_for_merits():
    d = process_claim(_personal(merits_accepted=None), [], _book(), _rs(), TODAY)
    assert d["disposition"] == "MERITS"        # merits_pending injects MERITS
    assert d["eligible_to_pay"] is False
    assert "held_for_merits" in d["holds"]
    assert "held_merits" in d["holds"]         # disposition MERITS not in {CLEAN, ADJUSTED}
    assert d["band"] == "GREEN"                # no scored reasons
    assert d["medical_payable"] == 500.0


def test_merits_accepted_personal_clean_eligible():
    d = process_claim(_personal(merits_accepted=True, fault_pct=0.0), [], _book(), _rs(), TODAY)
    assert d["disposition"] == "CLEAN"
    assert d["eligible_to_pay"] is True
    assert d["holds"] == []
    assert d["net_payable"] == 500.0


def test_personal_apportioned_medical_halved_by_fault():
    d = process_claim(_personal(merits_accepted=True, fault_pct=25.0), [], _book(), _rs(), TODAY)
    # 500 * 0.75 = 375.0
    assert d["medical_payable"] == 375.0
    assert d["net_payable"] == 375.0


# ── compliance / gate-driven records ─────────────────────────────────────────
def test_oar_missing_invalidates_and_holds():
    c = _personal(merits_accepted=True,
                  documents={"RAF1": True, "OAR": False, "ID": True, "BANK": True})
    d = process_claim(c, [], _book(), _rs(), TODAY)
    assert d["validated"] is False
    assert "OAR_MISSING" in d["reasons"]
    assert d["disposition"] == "COMPLIANCE"
    assert d["eligible_to_pay"] is False
    assert "held_for_validation" in d["holds"]
    assert "held_compliance" in d["holds"]


def test_over_reference_supplier_reprices_and_marks_adjusted():
    # billed 800 vs rpl 500 -> BILLED_OVER_REFERENCE, reprice 500, ADJUSTED (still payable)
    d = process_claim(_supplier(lines=[_line(code="0190", amount=800.0)]), [], _book(), _rs(), TODAY)
    assert "BILLED_OVER_REFERENCE" in d["reasons"]
    assert d["disposition"] == "ADJUSTED"
    assert d["medical_payable"] == 500.0
    assert d["eligible_to_pay"] is True        # ADJUSTED is payable
    assert d["net_payable"] == 500.0


def test_merits_rejected_personal_records_ground():
    d = process_claim(_personal(merits_accepted=False, merits_ground="S19_EXCLUSION"),
                      [], _book(), _rs(), TODAY)
    assert "S19_EXCLUSION" in d["reasons"]
    assert d["disposition"] == "MERITS"
    assert d["eligible_to_pay"] is False


def test_shadow_signal_surfaces_in_shadow_not_reasons():
    # thin convergence accident (SAPS only) -> CONVERGENCE_THIN is SHADOW
    acc = Accident(accident_id="A_pre", case_number="CAS100/02/2026", when=date(2026, 2, 1),
                   where="", vehicles=set(), parties={"P_1"}, oar_occupants=5, sources={"SAPS": "c1"})
    d = process_claim(_supplier(), [acc], _book(), _rs(), TODAY)
    assert "CONVERGENCE_THIN" in d["shadow_signals"]
    assert "CONVERGENCE_THIN" not in d["reasons"]
    assert d["score"] == 0                     # shadow contributes zero
    assert d["convergence"] == 4.2             # 0.5/12*100


# ── 2026-11-09 High findings threaded through the pipeline ───────────────────
def test_h2_prior_lines_preclude_and_ledger_accumulates():
    from engine.adjudication import line_key
    ledger = {line_key("P_1", _line())}
    d = process_claim(_supplier(lines=[_line(), _line(amount=300.0)]), [], _book(), _rs(), TODAY,
                      seen_lines=ledger)
    assert d["reasons"] == ["SUPPLIER_PRECLUSION"] and d["disposition"] == "ADJUSTED"
    assert d["medical_payable"] == 300.0
    assert line_key("P_1", _line(amount=300.0)) in ledger       # this claim's line now in the ledger


def test_h2_duplicate_personal_claim_on_same_accident():
    acc = Accident(accident_id="A_pre", case_number="CAS100/02/2026", when=date(2026, 2, 1),
                   where="", vehicles=set(), parties={"P_1"}, oar_occupants=5,
                   sources={"EMS": "c1", "HOSPITAL": "c2", "SAPS": "c3"}, claimants={"P_1"})
    d = process_claim(_personal(merits_accepted=True), [acc], _book(), _rs(), TODAY)
    assert "DUPLICATE_CLAIM" in d["reasons"] and d["disposition"] == "COMPLIANCE"
    assert d["eligible_to_pay"] is False and "held_compliance" in d["holds"]


def test_h2_first_personal_claim_registers_claimant():
    acc = Accident(accident_id="A_pre", case_number="CAS100/02/2026", when=date(2026, 2, 1),
                   where="", vehicles=set(), parties={"P_1"}, oar_occupants=5,
                   sources={"EMS": "c1", "HOSPITAL": "c2", "SAPS": "c3"})
    d = process_claim(_personal(merits_accepted=True), [acc], _book(), _rs(), TODAY)
    assert "DUPLICATE_CLAIM" not in d["reasons"] and acc.claimants == {"P_1"}


def test_h5_advisory_signal_in_record_and_not_dispositive():
    d = process_claim(_supplier(lines=[_line(dx="K35")]), [], _book(), _rs(), TODAY,
                      accident_dx_regions={"S72"},
                      mode_overrides={"DX_ACCIDENT_MISMATCH": SignalMode.ADVISORY})
    assert d["reasons"] == ["DX_ACCIDENT_MISMATCH"] and d["advisory_signals"] == ["DX_ACCIDENT_MISMATCH"]
    assert d["disposition"] == "CLEAN" and d["eligible_to_pay"] is True


def test_h5_single_green_heuristic_is_not_fraud():
    d = process_claim(_supplier(lines=[_line(dx="K35")]), [], _book(), _rs(), TODAY,
                      accident_dx_regions={"S72"})
    assert d["score"] == 15 and d["band"] == "GREEN"
    assert d["disposition"] == "CLEAN" and d["eligible_to_pay"] is True


def test_h6_uncovered_code_is_held_for_review_with_flag():
    d = process_claim(_supplier(lines=[_line(code="7777", amount=1e12)]), [], _book(), _rs(), TODAY)
    assert d["needs_review"] is True and d["reasons"] == ["REFERENCE_UNRESOLVED"]
    assert d["disposition"] == "REVIEW" and d["eligible_to_pay"] is False
    assert d["holds"] == ["held_review"]


def test_h7_worklist_match_creates_own_accident_and_names_candidate():
    acc = Accident(accident_id="A_pre", case_number="CAS999/01/2020", when=date(2026, 2, 1),
                   where="", vehicles=set(), parties={"P_1"}, oar_occupants=None,
                   sources={"EMS": "c1", "HOSPITAL": "c2"})
    d = process_claim(_supplier(case_number_raw=None), [acc], _book(), _rs(), TODAY)
    assert d["accident_action"] == "WORKLIST" and d["accident_id"] == "A_R_1"
    assert d["accident_candidate"] == "A_pre" and "R_1" not in acc.claims


def test_h8_grounded_gate_shadow_override_ignored():
    d = process_claim(_personal(merits_accepted=True, accident_date=date(2020, 1, 1),
                                lodged_on=date(2024, 1, 1)), [], _book(), _rs(), TODAY,
                      mode_overrides={"PRESCRIBED_LODGEMENT": SignalMode.SHADOW})
    assert "PRESCRIBED_LODGEMENT" in d["reasons"] and d["disposition"] == "COMPLIANCE"


def test_h12_apportioned_medical_rounds_half_up():
    d = process_claim(_personal(merits_accepted=True, fault_pct=30.0, lines=[_line(amount=100.05)]),
                      [], _book(), _rs(), TODAY)
    assert d["medical_payable"] == 70.04 and d["net_payable"] == 70.04
