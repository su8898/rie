"""Per-function unit tests for engine.adjudication — concrete value assertions.

Codes compare normalised everywhere (H3): Ruleset.preauth_required, Authorisation.codes and
RefBook.non_benchmarkable are normalised on construction, and adjudicate_line normalises the
line code before the pre-auth, authorisation and duplicate checks — so "500" cannot bypass a
"0500" pre-auth requirement and "0190" + "190" cannot both pay.
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
        rpl={"190": {"GP": 500.0, "SPECIALIST": 700.0}},
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


def test_reference_uncovered_needs_review_is_a_hard_review_gate():
    # H6: an uncovered code carries the billed figure forward but is never paid as billed —
    # REFERENCE_UNRESOLVED (hard, REVIEW) routes the claim to R&N review and holds payment
    lr = adjudicate_line(_claim(), _line(code="7777", amount=500.0), _book(), _rs(), "GP", set(), set())
    assert (lr.payable, lr.reasons, lr.src, lr.needs_review) == (500.0, ["REFERENCE_UNRESOLVED"], "—", True)


def test_dx_mismatch_note_survives_into_reference_reprice():
    # mismatch note carried through to a repricing decision
    lr = adjudicate_line(_claim(), _line(code="0190", amount=800.0, dx="K35"),
                         _book(), _rs(), "GP", set(), {"S72"})
    assert lr.reasons == ["DX_ACCIDENT_MISMATCH", "BILLED_OVER_REFERENCE"]
    assert lr.payable == 500.0


# ── H2: the cross-claim pay-once ledger (s17(5)) ─────────────────────────────
def test_prior_line_from_another_claim_is_supplier_preclusion():
    from engine.adjudication import line_key
    prior = frozenset({line_key("P_1", _line())})
    lr = adjudicate_line(_claim(), _line(), _book(), _rs(), "GP", set(), set(), prior)
    assert (lr.payable, lr.reasons, lr.src) == (0.0, ["SUPPLIER_PRECLUSION"], "—")


def test_line_key_normalises_code_and_carries_kind():
    from engine.adjudication import line_key
    assert line_key("P_1", _line(code="0190")) == line_key("P_1", _line(code="190"))
    assert line_key("P_1", _line(code="190")) != line_key("P_1", _line(kind="NAPPI", code="190"))


# ── H3: one code identity ────────────────────────────────────────────────────
def test_preauth_required_matches_normalised_code():
    c = _claim(claim_type="UNDERTAKING_INVOICE",
               undertaking=Undertaking(active=True, scope_dx={"S72"}, scope_coded=True))
    lr = adjudicate_line(c, _line(code="500", amount=500.0), _book(), _rs(), "GP", set(), set())
    assert lr.reasons == ["PREAUTH_MISSING"] and lr.payable == 0.0


def test_duplicate_line_across_leading_zero_variants():
    seen: set = set()
    adjudicate_line(_claim(), _line(code="0190"), _book(), _rs(), "GP", seen, set())
    lr = adjudicate_line(_claim(), _line(code="190"), _book(), _rs(), "GP", seen, set())
    assert lr.reasons == ["DUPLICATE_LINE"] and lr.payable == 0.0


def test_authorisation_codes_normalised_on_construction():
    auth = _auth(codes={"0190", "55"})
    assert auth.codes == {"190", "55"}
    assert find_authorisation(Undertaking(True, {"S72"}, True, [auth]), _line(code="190")) is auth


# ── H4: authorisation consumption across lines ───────────────────────────────
def test_ceiling_is_consumed_across_lines():
    from engine.adjudication import consume_authorisation
    auth, usage = _auth(ceiling=1000.0), {}
    assert consume_authorisation(auth, _line(amount=999.0), usage) == 999.0
    assert consume_authorisation(auth, _line(amount=998.0), usage) == 1.0
    assert consume_authorisation(auth, _line(amount=997.0), usage) == 0.0


def test_qty_limit_is_consumed_across_lines():
    from engine.adjudication import consume_authorisation
    auth, usage = _auth(qty_limit=3.0, ceiling=10000.0), {}
    assert consume_authorisation(auth, _line(qty=2.0, amount=200.0), usage) == 200.0
    assert consume_authorisation(auth, _line(qty=2.0, amount=200.0), usage) == 100.0   # 1 unit left
    assert consume_authorisation(auth, _line(qty=1.0, amount=100.0), usage) == 0.0


def test_qty_limit_zero_means_unlimited_units():
    from engine.adjudication import consume_authorisation
    auth, usage = _auth(qty_limit=0.0, ceiling=10000.0), {}
    assert consume_authorisation(auth, _line(qty=50.0, amount=5000.0), usage) == 5000.0


def test_non_positive_qty_is_treated_as_one_unit():
    from engine.adjudication import consume_authorisation
    auth, usage = _auth(qty_limit=1.0, ceiling=10000.0), {}
    assert consume_authorisation(auth, _line(qty=0.0, amount=400.0), usage) == 400.0
    assert consume_authorisation(auth, _line(qty=0.0, amount=400.0), usage) == 0.0


def test_adjudicate_line_tracks_usage_through_the_claim():
    u = Undertaking(True, {"S72"}, True, [_auth(ceiling=1000.0)])
    c = _claim(claim_type="UNDERTAKING_INVOICE", undertaking=u)
    usage: dict = {}
    first = adjudicate_line(c, _line(amount=999.0), _book(), _rs(), "GP", set(), set(), frozenset(), usage)
    second = adjudicate_line(c, _line(amount=998.0), _book(), _rs(), "GP", set(), set(), frozenset(), usage)
    assert (first.payable, first.reasons) == (999.0, [])
    assert (second.payable, second.reasons, second.src) == (1.0, ["PREAUTH_EXCEEDED"], "authorisation")


def test_adjudicate_line_without_usage_dict_still_prices_one_line():
    u = Undertaking(True, {"S72"}, True, [_auth(ceiling=300.0)])
    c = _claim(claim_type="UNDERTAKING_INVOICE", undertaking=u)
    lr = adjudicate_line(c, _line(amount=500.0), _book(), _rs(), "GP", set(), set())
    assert (lr.payable, lr.reasons) == (300.0, ["PREAUTH_EXCEEDED"])


# ── H12: exact money ─────────────────────────────────────────────────────────
def test_expected_reference_is_exact_decimal():
    # RPL 500 x qty 3 = 1500.00 exactly; billed 1500.001 is over by a sub-cent -> still repriced
    lr = adjudicate_line(_claim(), _line(qty=3.0, amount=1500.001), _book(), _rs(), "GP", set(), set())
    assert (lr.payable, lr.reasons) == (1500.0, ["BILLED_OVER_REFERENCE"])
