"""Per-function unit tests for engine.reference — concrete value assertions.

Every expected number is computed by hand from reference.py's logic. Note the tariff-code
normalisation: `resolve` strips leading zeros for kind=='TARIFF' (nc = code.lstrip("0")),
so a RefBook meant to answer for line code '0190' must key its rpl/raf2022 dicts on the
*normalised* '190'. negotiated/empirical are keyed on (kind, nc). NAPPI is never normalised.
"""
from __future__ import annotations

import pytest

from engine.reference import (
    DISP_FEE_FLAT, GAZETTE_FLOOR, OCR_SUSPECT_RATIO, RefBook, dispensing_fee, resolve,
)
from engine.vocab import LegalStatus


def _book(**over) -> RefBook:
    base = dict(
        negotiated={("TARIFF", "55"): 400.0, ("NAPPI", "NEG1"): 12.0},
        rpl={"190": {"GP": 500.0, "SPECIALIST": 700.0}, "23": {"GP": 100.0}},
        raf2022={"200": 300.0, "300": 50.0, "400": 5.0},
        empirical={("TARIFF", "999"): 250.0, ("TARIFF", "300"): 300.0, ("NAPPI", "888"): 90.0},
        sep={"700101": 88.40, "700200": 200.0},
        non_benchmarkable={"NB1"},
    )
    base.update(over)
    return RefBook(**base)


# ── dispensing_fee ───────────────────────────────────────────────────────────
def test_dispensing_fee_below_threshold_is_30_percent():
    # 100.0 < 155.0 -> round(100*0.30, 2) == 30.0
    assert dispensing_fee(100.0) == 30.0


def test_dispensing_fee_below_threshold_rounds_to_2dp():
    # 88.40 < 155.0 -> round(88.40*0.30, 2) == round(26.52, 2) == 26.52
    assert dispensing_fee(88.40) == 26.52


def test_dispensing_fee_at_threshold_is_flat():
    # 155.0 is NOT < 155.0 -> flat 46.50
    assert dispensing_fee(155.0) == DISP_FEE_FLAT == 46.50


def test_dispensing_fee_above_threshold_is_flat():
    assert dispensing_fee(1000.0) == 46.50


def test_dispensing_fee_just_below_threshold_is_percent():
    # 154.0 < 155.0 -> round(154*0.30,2) == 46.2 (proves the < branch, not the flat)
    assert dispensing_fee(154.0) == 46.2


# ── resolve: negotiated ──────────────────────────────────────────────────────
def test_resolve_negotiated_enforceable():
    # code '0055' -> nc '55' -> negotiated[('TARIFF','55')] == 400.0
    assert resolve(_book(), "TARIFF", "0055") == (400.0, "negotiated", LegalStatus.ENFORCEABLE)


def test_resolve_negotiated_nappi_not_normalised():
    # NAPPI codes are not stripped; ('NAPPI','NEG1') hit
    assert resolve(_book(), "NAPPI", "NEG1") == (12.0, "negotiated", LegalStatus.ENFORCEABLE)


# ── resolve: RPL ─────────────────────────────────────────────────────────────
def test_resolve_rpl_gp():
    # '0190' -> '190' -> rpl gp 500.0
    assert resolve(_book(), "TARIFF", "0190") == (500.0, "RPL", LegalStatus.ACCEPTED)


def test_resolve_rpl_specialist_uses_spec_rate():
    # tier SPECIALIST with a spec rate present -> 700.0
    assert resolve(_book(), "TARIFF", "0190", "SPECIALIST") == (700.0, "RPL", LegalStatus.ACCEPTED)


def test_resolve_rpl_specialist_falls_back_to_gp_when_no_spec_rate():
    # code '0023' -> '23' -> (100.0, None); spec is None -> falls back to gp 100.0
    assert resolve(_book(), "TARIFF", "0023", "SPECIALIST") == (100.0, "RPL", LegalStatus.ACCEPTED)


def test_resolve_rpl_gp_tier_ignores_spec_rate():
    # default tier GP -> gp rate even though a spec rate exists
    assert resolve(_book(), "TARIFF", "0190", "GP")[0] == 500.0


def test_resolve_rpl_discipline_specific():
    # a code priced per discipline -> the billing discipline's rate
    book = _book(rpl={"190": {"GP": 10.6, "CHIRO": 399.06}})
    assert resolve(book, "TARIFF", "0190", "CHIRO")[0] == 399.06
    assert resolve(book, "TARIFF", "0190", "GP")[0] == 10.6


def test_resolve_rpl_falls_back_to_cheapest_when_no_gp():
    # discipline absent AND no GP schedule -> cheapest rate (conservative)
    book = _book(rpl={"190": {"CHIRO": 399.06, "DENTAL": 120.0}})
    assert resolve(book, "TARIFF", "0190", "PHYSIO")[0] == 120.0


# ── resolve: RAF 2022 interdicted ────────────────────────────────────────────
def test_resolve_raf2022_interdicted():
    # '0200' -> '200' -> raf2022 300.0 (>= GAZETTE_FLOOR 10); no empirical for ('TARIFF','200')
    assert resolve(_book(), "TARIFF", "0200") == (300.0, "RAF 2022", LegalStatus.INTERDICTED)


def test_resolve_raf2022_below_gazette_floor_falls_through_to_uncovered():
    # '0400' -> '400' -> raf2022 5.0 < GAZETTE_FLOOR (10) -> skip; no other tier -> uncovered
    assert 5.0 < GAZETTE_FLOOR
    assert resolve(_book(), "TARIFF", "0400") == (None, "—", None)


# ── resolve: OCR dropped-digit guard ─────────────────────────────────────────
def test_resolve_ocr_guard_returns_empirical_endogenous():
    # '0300' -> '300' -> raf2022 50.0 (>=10); empirical ('TARIFF','300')=300.0.
    # 50 < 0.33*300 == 99.0 -> OCR suspect -> return empirical 300.0 ENDOGENOUS
    assert 50.0 < OCR_SUSPECT_RATIO * 300.0
    assert resolve(_book(), "TARIFF", "0300") == (300.0, "empirical", LegalStatus.ENDOGENOUS)


def test_resolve_no_ocr_guard_when_gazette_not_suspiciously_low():
    # raf2022 '300' raised to 200 so 200 >= 0.33*300 (99) -> NOT suspect -> INTERDICTED at 200
    book = _book(raf2022={"200": 300.0, "300": 200.0, "400": 5.0})
    assert resolve(book, "TARIFF", "0300") == (200.0, "RAF 2022", LegalStatus.INTERDICTED)


# ── resolve: NAPPI SEP+fee ───────────────────────────────────────────────────
def test_resolve_nappi_sep_plus_fee_enforceable():
    # sep 88.40 -> fee round(88.40*0.30,2)=26.52 -> round(88.40+26.52,2)=114.92
    assert resolve(_book(), "NAPPI", "700101") == (114.92, "NAPPI+fee", LegalStatus.ENFORCEABLE)


def test_resolve_nappi_sep_plus_flat_fee_when_sep_high():
    # sep 200.0 >= 155 -> flat fee 46.50 -> 200+46.50 = 246.50
    assert resolve(_book(), "NAPPI", "700200") == (246.50, "NAPPI+fee", LegalStatus.ENFORCEABLE)


# ── resolve: empirical fallback ──────────────────────────────────────────────
def test_resolve_empirical_fallback_tariff():
    # '0999' -> '999'; not negotiated/rpl/raf2022 -> empirical ('TARIFF','999')=250.0
    assert resolve(_book(), "TARIFF", "0999") == (250.0, "empirical", LegalStatus.ENDOGENOUS)


def test_resolve_empirical_fallback_nappi():
    # NAPPI '888' not in sep -> empirical ('NAPPI','888')=90.0
    assert resolve(_book(), "NAPPI", "888") == (90.0, "empirical", LegalStatus.ENDOGENOUS)


# ── resolve: non_benchmarkable guard (fires first) ───────────────────────────
def test_resolve_non_benchmarkable_returns_none_triple():
    assert resolve(_book(), "TARIFF", "NB1") == (None, "—", None)


def test_resolve_non_benchmarkable_guard_beats_a_real_rate():
    # code would resolve via rpl, but it is also non_benchmarkable -> guard wins, no overage
    book = _book(non_benchmarkable={"0190"})
    assert resolve(book, "TARIFF", "0190") == (None, "—", None)


# ── resolve: uncovered ───────────────────────────────────────────────────────
def test_resolve_uncovered_code_returns_none_triple():
    assert resolve(_book(), "TARIFF", "7777") == (None, "—", None)


def test_resolve_uncovered_nappi_returns_none_triple():
    assert resolve(_book(), "NAPPI", "ZZZ") == (None, "—", None)


# ── tariff normalisation ─────────────────────────────────────────────────────
def test_resolve_leading_zeros_stripped_equivalent_codes():
    # '0055', '055', '55' all normalise to '55' -> same negotiated answer
    ans = (400.0, "negotiated", LegalStatus.ENFORCEABLE)
    assert resolve(_book(), "TARIFF", "0055") == ans
    assert resolve(_book(), "TARIFF", "055") == ans
    assert resolve(_book(), "TARIFF", "55") == ans


def test_resolve_all_zero_code_normalises_to_single_zero():
    # '0000'.lstrip('0') == '' -> `or '0'` -> '0'. Keyed empirical ('TARIFF','0') resolves.
    book = _book(empirical={("TARIFF", "0"): 42.0})
    assert resolve(book, "TARIFF", "0000") == (42.0, "empirical", LegalStatus.ENDOGENOUS)


def test_resolve_nappi_not_normalised_leading_zero_matters():
    # NAPPI '0888' is NOT stripped -> ('NAPPI','888') miss -> uncovered
    assert resolve(_book(), "NAPPI", "0888") == (None, "—", None)


def test_resolve_precedence_negotiated_over_rpl():
    # a code present in BOTH negotiated and rpl resolves via negotiated (checked first)
    book = _book(negotiated={("TARIFF", "190"): 999.0}, rpl={"190": (500.0, 700.0)})
    assert resolve(book, "TARIFF", "0190") == (999.0, "negotiated", LegalStatus.ENFORCEABLE)
