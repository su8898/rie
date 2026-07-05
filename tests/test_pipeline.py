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

TODAY = date(2026, 7, 5)


def _book(**over) -> RefBook:
    base = dict(
        negotiated={("TARIFF", "55"): 400.0},
        rpl={"190": (500.0, 700.0)},
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
    assert d["accident_id"] == "A_1"          # no accident passed -> minted
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
