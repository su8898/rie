"""Per-function unit tests for engine.payments — concrete value assertions.

eligible_to_pay returns (ok, net_payable, holds).
  held_<disp>            when disposition not in {CLEAN, ADJUSTED}
  held_for_validation    when not validated
  held_for_merits        when PERSONAL and merits_accepted is not True
  PAYEE_UNVERIFIED       when not payee_verified
  ATTORNEY_NOT_IN_STANDING when not attorney_in_standing
  LIFE_STATUS_MISMATCH   when claimant_deceased_on set
net_payable = round(max(payable - interim_paid, 0.0), 2). ok == (no holds).
"""
from __future__ import annotations

from datetime import date

from engine.models import Claim
from engine.payments import eligible_to_pay
from engine.vocab import Category


def _claim(**over) -> Claim:
    base = dict(claim_id="R", claim_type="SUPPLIER", party_token="P",
                accident_date=date(2026, 2, 1), lodged_on=date(2026, 3, 1),
                case_number_raw=None, documents={}, lines=[],
                payee_verified=True, attorney_in_standing=True, provider_registered=True)
    base.update(over)
    return Claim(**base)


# ── all-clear ────────────────────────────────────────────────────────────────
def test_all_clear_supplier_eligible():
    ok, net, holds = eligible_to_pay(_claim(), Category.CLEAN, True, 0.0, 500.0)
    assert (ok, net, holds) == (True, 500.0, [])


def test_adjusted_disposition_allowed():
    ok, net, holds = eligible_to_pay(_claim(), Category.ADJUSTED, True, 0.0, 500.0)
    assert (ok, holds) == (True, [])


def test_personal_merits_accepted_all_clear():
    ok, net, holds = eligible_to_pay(
        _claim(claim_type="PERSONAL", merits_accepted=True), Category.CLEAN, True, 0.0, 500.0)
    assert (ok, holds) == (True, [])


# ── each hold ────────────────────────────────────────────────────────────────
def test_held_for_disposition_fraud():
    ok, _, holds = eligible_to_pay(_claim(), Category.FRAUD, True, 0.0, 500.0)
    assert not ok and holds == ["held_fraud"]


def test_held_for_disposition_merits():
    ok, _, holds = eligible_to_pay(_claim(), Category.MERITS, True, 0.0, 500.0)
    assert holds == ["held_merits"]


def test_held_for_disposition_compliance():
    ok, _, holds = eligible_to_pay(_claim(), Category.COMPLIANCE, True, 0.0, 500.0)
    assert holds == ["held_compliance"]


def test_held_for_disposition_preauth():
    ok, _, holds = eligible_to_pay(_claim(), Category.PREAUTH, True, 0.0, 500.0)
    assert holds == ["held_preauth"]


def test_held_for_disposition_si_gate():
    ok, _, holds = eligible_to_pay(_claim(), Category.SI_GATE, True, 0.0, 500.0)
    assert holds == ["held_si_gate"]


def test_held_for_validation():
    ok, _, holds = eligible_to_pay(_claim(), Category.CLEAN, False, 0.0, 500.0)
    assert holds == ["held_for_validation"]


def test_held_for_merits_personal_pending():
    ok, _, holds = eligible_to_pay(
        _claim(claim_type="PERSONAL", merits_accepted=None), Category.CLEAN, True, 0.0, 500.0)
    assert holds == ["held_for_merits"]


def test_held_for_merits_personal_rejected():
    ok, _, holds = eligible_to_pay(
        _claim(claim_type="PERSONAL", merits_accepted=False), Category.CLEAN, True, 0.0, 500.0)
    assert holds == ["held_for_merits"]


def test_no_merits_hold_for_supplier_even_if_not_accepted():
    # supplier claim: merits hold only applies to PERSONAL
    ok, _, holds = eligible_to_pay(
        _claim(claim_type="SUPPLIER", merits_accepted=None), Category.CLEAN, True, 0.0, 500.0)
    assert holds == []


def test_payee_unverified():
    ok, _, holds = eligible_to_pay(_claim(payee_verified=False), Category.CLEAN, True, 0.0, 500.0)
    assert holds == ["PAYEE_UNVERIFIED"]


def test_attorney_not_in_standing():
    ok, _, holds = eligible_to_pay(_claim(attorney_in_standing=False), Category.CLEAN, True, 0.0, 500.0)
    assert holds == ["ATTORNEY_NOT_IN_STANDING"]


def test_life_status_mismatch():
    ok, _, holds = eligible_to_pay(
        _claim(claimant_deceased_on=date(2026, 3, 1)), Category.CLEAN, True, 0.0, 500.0)
    assert holds == ["LIFE_STATUS_MISMATCH"]


def test_multiple_holds_accumulate_in_order():
    c = _claim(claim_type="PERSONAL", merits_accepted=None, payee_verified=False,
               attorney_in_standing=False, claimant_deceased_on=date(2026, 3, 1))
    ok, _, holds = eligible_to_pay(c, Category.FRAUD, False, 0.0, 500.0)
    assert ok is False
    assert holds == [
        "held_fraud", "held_for_validation", "held_for_merits",
        "PAYEE_UNVERIFIED", "ATTORNEY_NOT_IN_STANDING", "LIFE_STATUS_MISMATCH",
    ]


# ── net_payable arithmetic ───────────────────────────────────────────────────
def test_net_payable_nets_interim():
    _, net, _ = eligible_to_pay(_claim(), Category.CLEAN, True, 200.0, 500.0)
    assert net == 300.0


def test_net_payable_floored_at_zero():
    _, net, _ = eligible_to_pay(_claim(), Category.CLEAN, True, 800.0, 500.0)
    assert net == 0.0


def test_net_payable_rounds_to_2dp():
    # 500.00 - 100.12 = 399.88
    _, net, _ = eligible_to_pay(_claim(), Category.CLEAN, True, 100.12, 500.0)
    assert net == 399.88


def test_net_payable_reported_even_when_held():
    # holds do not zero out net; the amount is still computed
    _, net, holds = eligible_to_pay(_claim(), Category.FRAUD, True, 100.0, 500.0)
    assert net == 400.0 and holds == ["held_fraud"]
