"""Per-function unit tests for engine.heads — concrete value assertions.

apportion(amount, fault) = round(amount * (1 - (fault or 0)/100), 2).
Loss-of-earnings caps each year at cap_at(accident_date) THEN apportions (Sweatman order).
"""
from __future__ import annotations

from datetime import date

import pytest

from engine.heads import apportion, head_general_damages, head_loss_of_earnings, head_past_medical
from engine.models import Claim, LineResult, Ruleset


def _claim(**over) -> Claim:
    base = dict(claim_id="R", claim_type="PERSONAL", party_token="P",
                accident_date=date(2020, 6, 1), lodged_on=date(2020, 7, 1),
                case_number_raw=None, documents={}, lines=[])
    base.update(over)
    return Claim(**base)


def _lr(payable: float) -> LineResult:
    return LineResult(payable=payable, reasons=[], src="x")


# ── apportion ────────────────────────────────────────────────────────────────
def test_apportion_none_fault_full():
    assert apportion(100.0, None) == 100.0


def test_apportion_zero_fault_full():
    assert apportion(100.0, 0.0) == 100.0


def test_apportion_25_percent():
    assert apportion(100.0, 25.0) == 75.0


def test_apportion_100_percent_zero():
    assert apportion(100.0, 100.0) == 0.0


def test_apportion_rounds_to_2dp():
    # 33.33 * (1 - 10/100) = 29.997 -> round 30.0
    assert apportion(33.33, 10.0) == 30.0


# ── head_past_medical ────────────────────────────────────────────────────────
def test_head_past_medical_sum_then_apportion():
    # (100 + 200 + 50) = 350 * 0.75 = 262.5
    assert head_past_medical([_lr(100.0), _lr(200.0), _lr(50.0)], 25.0) == 262.5


def test_head_past_medical_no_fault_is_full_sum():
    assert head_past_medical([_lr(100.0), _lr(200.0)], None) == 300.0


def test_head_past_medical_empty_is_zero():
    assert head_past_medical([], 25.0) == 0.0


# ── head_loss_of_earnings ────────────────────────────────────────────────────
def _rs_two_epochs() -> Ruleset:
    # accident-date 2020-06-01 -> latest cap effective is the 2015 one (160000), NOT 2026's
    return Ruleset(caps=[(date(2015, 1, 1), 160000.0), (date(2026, 1, 31), 378581.0)])


def test_loss_of_earnings_picks_accident_date_cap():
    total, ws = head_loss_of_earnings([200000.0, 100000.0], _claim(fault_pct=25.0), _rs_two_epochs())
    # each year's cap is the 2015 epoch 160000 (2026 epoch is after the accident date)
    assert ws[0]["cap"] == 160000.0 and ws[1]["cap"] == 160000.0


def test_loss_of_earnings_worksheet_rows_correct():
    _, ws = head_loss_of_earnings([200000.0, 100000.0], _claim(fault_pct=25.0), _rs_two_epochs())
    assert ws == [
        {"year": 1, "loss": 200000.0, "cap": 160000.0, "capped": 160000.0},  # min(200000,160000)
        {"year": 2, "loss": 100000.0, "cap": 160000.0, "capped": 100000.0},  # min(100000,160000)
    ]


def test_loss_of_earnings_caps_then_apportions_total():
    total, _ = head_loss_of_earnings([200000.0, 100000.0], _claim(fault_pct=25.0), _rs_two_epochs())
    # (160000 + 100000) = 260000 * 0.75 = 195000.0
    assert total == 195000.0


def test_loss_of_earnings_no_fault_full():
    total, _ = head_loss_of_earnings([200000.0, 100000.0], _claim(fault_pct=None), _rs_two_epochs())
    assert total == 260000.0


def test_loss_of_earnings_empty_losses_zero():
    total, ws = head_loss_of_earnings([], _claim(fault_pct=25.0), _rs_two_epochs())
    assert total == 0.0 and ws == []


def test_loss_of_earnings_accident_after_second_epoch_uses_new_cap():
    c = _claim(accident_date=date(2026, 6, 1), fault_pct=0.0)
    total, ws = head_loss_of_earnings([500000.0], c, _rs_two_epochs())
    # now the 2026 epoch (378581) applies; min(500000, 378581) = 378581
    assert ws[0]["cap"] == 378581.0 and total == 378581.0


# ── head_general_damages ─────────────────────────────────────────────────────
def test_gd_no_si_returns_zero_and_reason():
    assert head_general_damages(_claim(si_accepted=None), 100000.0, 200000.0, 150000.0) == \
        (0.0, ["GENERAL_DAMAGES_NO_SI"])


def test_gd_si_false_also_no_si():
    assert head_general_damages(_claim(si_accepted=False), 100000.0, 200000.0, 150000.0) == \
        (0.0, ["GENERAL_DAMAGES_NO_SI"])


def test_gd_within_band_note_free():
    # p25 100000 <= 150000 <= p75 200000 -> no note; fault 0 -> full 150000
    assert head_general_damages(_claim(si_accepted=True, fault_pct=0.0), 100000.0, 200000.0, 150000.0) == \
        (150000.0, [])


def test_gd_outside_band_note():
    # 250000 > p75 200000 -> note; fault 0 -> full 250000
    assert head_general_damages(_claim(si_accepted=True, fault_pct=0.0), 100000.0, 200000.0, 250000.0) == \
        (250000.0, ["GD_OUTSIDE_BAND_NOTE"])


def test_gd_below_band_note():
    # 50000 < p25 100000 -> outside band note
    assert head_general_damages(_claim(si_accepted=True, fault_pct=0.0), 100000.0, 200000.0, 50000.0) == \
        (50000.0, ["GD_OUTSIDE_BAND_NOTE"])


def test_gd_within_band_apportioned():
    # within band, fault 50 -> 150000 * 0.5 = 75000
    assert head_general_damages(_claim(si_accepted=True, fault_pct=50.0), 100000.0, 200000.0, 150000.0) == \
        (75000.0, [])


def test_gd_boundary_values_are_within_band():
    # proposed == p25 (inclusive) -> no note
    assert head_general_damages(_claim(si_accepted=True, fault_pct=0.0), 100000.0, 200000.0, 100000.0)[1] == []
    # proposed == p75 (inclusive) -> no note
    assert head_general_damages(_claim(si_accepted=True, fault_pct=0.0), 100000.0, 200000.0, 200000.0)[1] == []
