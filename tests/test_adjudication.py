"""Per-function unit tests for engine.adjudication — concrete value assertions.

Key subtlety: adjudicate_line does NOT normalise codes for rs.preauth_required or
Authorisation.codes — those match the RAW line code. Only resolve() (called for reference
pricing) strips leading zeros. So the RefBook is keyed on normalised tariff codes, while
preauth_required / auth.codes are keyed on the exact line code.
"""
from __future__ import annotations

from datetime import date

import pytest

from engine.adjudication import adjudicate_line, find_authorisation
from engine.models import Authorisation, Claim, Line, Ruleset, Undertaking
from engine.reference import RefBook


def _book(**over) -> RefBook:
    base = dict(
        negotiated={("TARIFF", "55"): 400.0},
        rpl={"190": (500.0, 700.0)},
        raf2022={"200": 300.0, "300": 50.0},
        empirical={("TARIFF", "300"): 300.0, ("NAPPI", "888"): 90.0},
        sep={}, non_benchmarkable=set(),
    )
    base.update(over)
    return RefBook(**base)


def _rs(**over) -> Ruleset:
    base = dict(preauth_required={"0500"})
    base.update(over)
    return Ruleset(**base)


def _line(**over) -> Line:
    base = dict(kind="TARIFF", code="0190", qty=1.0, amount=500.0,
                service_date=date(2026, 3, 1), provider_id="PR1", dx="S72")
    base.update(over)
    return Line(**base)


def _claim(**over) -> Claim:
    base = dict(claim_id="R_1", claim_type="SUPPLIER", party_token="P_1",
                accident_date=date(2026, 2, 1), lodged_on=date(2026, 3, 1),
                case_number_raw=None, documents={}, lines=[])
    base.update(over)
    return Claim(**base)


def _auth(**over) -> Authorisation:
    base = dict(codes={"0190"}, qty_limit=10.0, ceiling=1000.0,
                valid_from=date(2026, 1, 1), valid_to=date(2026, 12, 31), status="APPROVED")
    base.update(over)
    return Authorisation(**base)


def _undertaking(**over) -> Undertaking:
    base = dict(active=True, scope_dx={"S72"}, scope_coded=True, authorisations=[])
    base.update(over)
    return Undertaking(**base)


# ── find_authorisation ───────────────────────────────────────────────────────
def test_find_authorisation_matches_code_status_date():
    u = _undertaking(authorisations=[_auth()])
    auth = find_authorisation(u, _line(code="0190", service_date=date(2026, 6, 1)))
    assert auth is not None and auth.ceiling == 1000.0


def test_find_authorisation_none_undertaking_returns_none():
    assert find_authorisation(None, _line()) is None


def test_find_authorisation_no_auths_returns_none():
    assert find_authorisation(_undertaking(authorisations=[]), _line()) is None


def test_find_authorisation_wrong_status_misses():
    u = _undertaking(authorisations=[_auth(status="PENDING")])
    assert find_authorisation(u, _line()) is None


def test_find_authorisation_date_before_range_misses():
    u = _undertaking(authorisations=[_auth(valid_from=date(2026, 5, 1))])
    assert find_authorisation(u, _line(service_date=date(2026, 3, 1))) is None


def test_find_authorisation_date_after_range_misses():
    u = _undertaking(authorisations=[_auth(valid_to=date(2026, 2, 1))])
    assert find_authorisation(u, _line(service_date=date(2026, 3, 1))) is None


def test_find_authorisation_wrong_code_misses():
    u = _undertaking(authorisations=[_auth(codes={"0999"})])
    assert find_authorisation(u, _line(code="0190")) is None


def test_find_authorisation_boundary_dates_inclusive():
    u = _undertaking(authorisations=[_auth(valid_from=date(2026, 3, 1), valid_to=date(2026, 3, 1))])
    assert find_authorisation(u, _line(service_date=date(2026, 3, 1))) is not None


# ── adjudicate_line: hard gates ──────────────────────────────────────────────
def test_service_before_accident():
    lr = adjudicate_line(_claim(), _line(service_date=date(2026, 1, 1)),
                         _book(), _rs(), "GP", set(), set())
    assert (lr.payable, lr.reasons, lr.src, lr.needs_review) == (0.0, ["SERVICE_BEFORE_ACCIDENT"], "—", False)


def test_duplicate_line_via_seen_set():
    seen: set = set()
    first = adjudicate_line(_claim(), _line(), _book(), _rs(), "GP", seen, set())
    assert first.reasons == []  # first pays through
    second = adjudicate_line(_claim(), _line(), _book(), _rs(), "GP", seen, set())
    assert (second.payable, second.reasons, second.src) == (0.0, ["DUPLICATE_LINE"], "—")


def test_dx_accident_mismatch_is_soft_and_pays():
    # dx K35 not in accident regions {S72}; billed 500 == rpl 500 -> no over -> only mismatch note
    lr = adjudicate_line(_claim(), _line(dx="K35", amount=500.0), _book(), _rs(),
                         "GP", set(), {"S72"})
    assert lr.reasons == ["DX_ACCIDENT_MISMATCH"]
    assert lr.payable == 500.0
    assert lr.needs_review is False


def test_no_dx_mismatch_when_accident_regions_empty():
    # empty regions -> guard `and accident_dx_regions` is falsy -> no mismatch
    lr = adjudicate_line(_claim(), _line(dx="K35"), _book(), _rs(), "GP", set(), set())
    assert "DX_ACCIDENT_MISMATCH" not in lr.reasons


# ── adjudicate_line: undertaking + preauth ───────────────────────────────────
def test_undertaking_not_active():
    c = _claim(claim_type="UNDERTAKING_INVOICE", undertaking=_undertaking(active=False))
    lr = adjudicate_line(c, _line(dx="S72"), _book(), _rs(), "GP", set(), set())
    assert (lr.payable, lr.reasons, lr.src) == (0.0, ["UNDERTAKING_NOT_ACTIVE"], "—")


def test_undertaking_missing_treated_as_not_active():
    c = _claim(claim_type="UNDERTAKING_INVOICE", undertaking=None)
    lr = adjudicate_line(c, _line(dx="S72"), _book(), _rs(), "GP", set(), set())
    assert lr.reasons == ["UNDERTAKING_NOT_ACTIVE"]


def test_undertaking_scope_coded_hard_reject():
    c = _claim(claim_type="UNDERTAKING_INVOICE", undertaking=_undertaking(scope_dx={"S72"}, scope_coded=True))
    lr = adjudicate_line(c, _line(code="0190", dx="K35"), _book(), _rs(), "GP", set(), set())
    assert (lr.payable, lr.reasons, lr.src) == (0.0, ["UNDERTAKING_SCOPE"], "—")


def test_undertaking_scope_uncoded_is_soft_and_prices():
    # uncoded scope: soft note, then reference pricing. rpl 190 = 500, billed 500 -> pays 500
    c = _claim(claim_type="UNDERTAKING_INVOICE", undertaking=_undertaking(scope_dx={"S72"}, scope_coded=False))
    lr = adjudicate_line(c, _line(code="0190", amount=500.0, dx="K35"), _book(), _rs(), "GP", set(), set())
    assert lr.reasons == ["UNDERTAKING_SCOPE"]
    assert lr.payable == 500.0


def test_undertaking_within_auth_pays_billed():
    u = _undertaking(scope_dx={"S72"}, scope_coded=True, authorisations=[_auth(ceiling=1000.0)])
    c = _claim(claim_type="UNDERTAKING_INVOICE", undertaking=u)
    lr = adjudicate_line(c, _line(code="0190", amount=500.0, dx="S72"), _book(), _rs(), "GP", set(), set())
    assert (lr.payable, lr.reasons, lr.src) == (500.0, [], "authorisation")


def test_undertaking_preauth_exceeded_reprices_to_ceiling():
    u = _undertaking(scope_dx={"S72"}, scope_coded=True, authorisations=[_auth(ceiling=300.0)])
    c = _claim(claim_type="UNDERTAKING_INVOICE", undertaking=u)
    lr = adjudicate_line(c, _line(code="0190", amount=500.0, dx="S72"), _book(), _rs(), "GP", set(), set())
    assert (lr.payable, lr.reasons, lr.src) == (300.0, ["PREAUTH_EXCEEDED"], "authorisation")


def test_undertaking_preauth_missing():
    # code 0500 in preauth_required, no matching auth, not emergency -> PREAUTH_MISSING
    u = _undertaking(scope_dx={"S72"}, scope_coded=True, authorisations=[])
    c = _claim(claim_type="UNDERTAKING_INVOICE", undertaking=u)
    lr = adjudicate_line(c, _line(code="0500", amount=500.0, dx="S72"), _book(), _rs(), "GP", set(), set())
    assert (lr.payable, lr.reasons, lr.src) == (0.0, ["PREAUTH_MISSING"], "—")


def test_undertaking_emergency_bypasses_preauth():
    # emergency skips the preauth block -> reference pricing. code 0500 uncovered -> needs_review
    u = _undertaking(scope_dx={"S72"}, scope_coded=True, authorisations=[])
    c = _claim(claim_type="UNDERTAKING_INVOICE", undertaking=u)
    lr = adjudicate_line(c, _line(code="0500", amount=500.0, dx="S72", emergency=True),
                         _book(), _rs(), "GP", set(), set())
    assert lr.payable == 500.0
    assert lr.needs_review is True
    assert "PREAUTH_MISSING" not in lr.reasons


def test_undertaking_in_scope_no_auth_not_preauth_prices_reference():
    # in-scope dx, no auth, code not in preauth_required -> reference pricing. rpl 190 500 == billed
    u = _undertaking(scope_dx={"S72"}, scope_coded=True, authorisations=[])
    c = _claim(claim_type="UNDERTAKING_INVOICE", undertaking=u)
    lr = adjudicate_line(c, _line(code="0190", amount=500.0, dx="S72"), _book(), _rs(), "GP", set(), set())
    assert (lr.payable, lr.reasons, lr.src) == (500.0, [], "RPL")


# ── adjudicate_line: reference pricing (SUPPLIER) ────────────────────────────
def test_reference_enforceable_reprice_min():
    # negotiated 0055 = 400 ENFORCEABLE, billed 500 -> reprice to 400
    lr = adjudicate_line(_claim(), _line(code="0055", amount=500.0), _book(), _rs(), "GP", set(), set())
    assert (lr.payable, lr.reasons, lr.src, lr.needs_review) == \
        (400.0, ["BILLED_OVER_REFERENCE"], "negotiated", False)


def test_reference_accepted_reprice_min():
    # rpl gp 500 ACCEPTED, billed 800 -> reprice 500
    lr = adjudicate_line(_claim(), _line(code="0190", amount=800.0), _book(), _rs(), "GP", set(), set())
    assert (lr.payable, lr.reasons, lr.src, lr.needs_review) == \
        (500.0, ["BILLED_OVER_REFERENCE"], "RPL", False)


def test_reference_accepted_specialist_reprice():
    lr = adjudicate_line(_claim(), _line(code="0190", amount=800.0), _book(), _rs(), "SPECIALIST", set(), set())
    assert lr.payable == 700.0 and lr.src == "RPL"


def test_reference_interdicted_signal_only_not_repriced():
    # raf2022 0200 = 300 INTERDICTED, billed 400 -> BILLED_OVER_REFERENCE but pays billed, needs_review
    lr = adjudicate_line(_claim(), _line(code="0200", amount=400.0), _book(), _rs(), "GP", set(), set())
    assert (lr.payable, lr.reasons, lr.src, lr.needs_review) == \
        (400.0, ["BILLED_OVER_REFERENCE"], "RAF 2022", True)


def test_reference_endogenous_signal_only_not_repriced():
    # 0300 -> OCR guard -> empirical 300 ENDOGENOUS, billed 400 -> signal only, pays billed
    lr = adjudicate_line(_claim(), _line(code="0300", amount=400.0), _book(), _rs(), "GP", set(), set())
    assert (lr.payable, lr.reasons, lr.src, lr.needs_review) == \
        (400.0, ["BILLED_OVER_REFERENCE"], "empirical", True)


def test_reference_under_reference_pays_billed_no_reason():
    lr = adjudicate_line(_claim(), _line(code="0190", amount=400.0), _book(), _rs(), "GP", set(), set())
    assert (lr.payable, lr.reasons, lr.src, lr.needs_review) == (400.0, [], "RPL", False)


def test_reference_at_reference_pays_billed_no_reason():
    lr = adjudicate_line(_claim(), _line(code="0190", amount=500.0), _book(), _rs(), "GP", set(), set())
    assert (lr.payable, lr.reasons) == (500.0, [])


def test_reference_qty_multiplies_expected_under():
    # expected = 500 * 2 = 1000; billed 900 <= 1000 -> pays 900
    lr = adjudicate_line(_claim(), _line(code="0190", qty=2.0, amount=900.0), _book(), _rs(), "GP", set(), set())
    assert (lr.payable, lr.reasons) == (900.0, [])


def test_reference_qty_multiplies_expected_over():
    # expected 1000; billed 1200 -> reprice to 1000
    lr = adjudicate_line(_claim(), _line(code="0190", qty=2.0, amount=1200.0), _book(), _rs(), "GP", set(), set())
    assert (lr.payable, lr.reasons) == (1000.0, ["BILLED_OVER_REFERENCE"])


def test_reference_uncovered_needs_review_pays_billed():
    lr = adjudicate_line(_claim(), _line(code="7777", amount=500.0), _book(), _rs(), "GP", set(), set())
    assert (lr.payable, lr.reasons, lr.src, lr.needs_review) == (500.0, [], "—", True)


def test_dx_mismatch_note_survives_into_reference_reprice():
    # mismatch note carried through to a repricing decision
    lr = adjudicate_line(_claim(), _line(code="0190", amount=800.0, dx="K35"),
                         _book(), _rs(), "GP", set(), {"S72"})
    assert lr.reasons == ["DX_ACCIDENT_MISMATCH", "BILLED_OVER_REFERENCE"]
    assert lr.payable == 500.0
