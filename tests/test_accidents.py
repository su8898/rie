"""Per-function unit tests for engine.accidents — concrete value assertions."""
from __future__ import annotations

from datetime import date

import pytest

from engine.accidents import AUTO_JOIN, WORKLIST, match_score, normalise_cas, resolve_accident
from engine.models import Accident, Claim


def _claim(**over) -> Claim:
    base = dict(
        claim_id="R_1", claim_type="SUPPLIER", party_token="P_1",
        accident_date=date(2026, 2, 1), lodged_on=date(2026, 3, 1),
        case_number_raw="CAS 100/02/2026", documents={}, lines=[],
    )
    base.update(over)
    return Claim(**base)


def _accident(**over) -> Accident:
    base = dict(
        accident_id="A_pre", case_number="CAS100/02/2026", when=date(2026, 2, 1),
        where="JHB", vehicles={"V1"}, parties={"P_1"}, oar_occupants=None, sources={},
    )
    base.update(over)
    return Accident(**base)


# ── normalise_cas ────────────────────────────────────────────────────────────
def test_normalise_cas_spaced_four_digit_year():
    assert normalise_cas("CAS 123/04/2026") == "CAS123/04/2026"


def test_normalise_cas_two_digit_year_expands_to_20xx():
    # '123/4/26' -> n=123, m='4'.zfill(2)='04', y='26' len 2 -> '2026'
    assert normalise_cas("123/4/26") == "CAS123/04/2026"


def test_normalise_cas_dash_separators_and_prefix():
    assert normalise_cas("cas123-4-2026") == "CAS123/04/2026"


def test_normalise_cas_none_returns_none():
    assert normalise_cas(None) is None


def test_normalise_cas_empty_string_returns_none():
    assert normalise_cas("") is None


def test_normalise_cas_fewer_than_three_groups_returns_none():
    assert normalise_cas("123/04") is None


def test_normalise_cas_no_digits_returns_none():
    assert normalise_cas("no digits here") is None


def test_normalise_cas_strips_leading_zeros_on_number_via_int():
    # int('007') == 7 -> 'CAS7/04/2026'
    assert normalise_cas("007/4/26") == "CAS7/04/2026"


def test_normalise_cas_month_zero_padded():
    # month '3' -> '03'
    assert normalise_cas("55/3/2026") == "CAS55/03/2026"


def test_normalise_cas_extra_groups_uses_first_three():
    # more than 3 groups: only first three used
    assert normalise_cas("12/3/2026/99") == "CAS12/03/2026"


# ── match_score ──────────────────────────────────────────────────────────────
def test_match_score_full_match_is_one():
    # date(±1)=0.40 + place=0.20 + vehicle=0.25 + party=0.15 == 1.0
    assert match_score(_claim(), _accident(), "JHB", {"V1"}) == pytest.approx(1.0)


def test_match_score_date_only_weight_040():
    a = _accident(where="X", vehicles=set(), parties=set())
    assert match_score(_claim(), a, "JHB", {"V1"}) == pytest.approx(0.40)


def test_match_score_place_weight_020():
    a = _accident(where="JHB", vehicles=set(), parties=set())
    # date 0.40 + place 0.20
    assert match_score(_claim(), a, "JHB", set()) == pytest.approx(0.60)


def test_match_score_vehicle_overlap_weight_025():
    a = _accident(where="X", vehicles={"V1", "V9"}, parties=set())
    # date 0.40 + vehicle overlap 0.25
    assert match_score(_claim(), a, "", {"V1"}) == pytest.approx(0.65)


def test_match_score_party_weight_015():
    a = _accident(where="X", vehicles=set(), parties={"P_1"})
    # date 0.40 + party 0.15
    assert match_score(_claim(party_token="P_1"), a, "", set()) == pytest.approx(0.55)


def test_match_score_date_outside_one_day_scores_zero_on_date():
    c = _claim(accident_date=date(2026, 2, 5))
    a = _accident(when=date(2026, 2, 1), where="JHB", vehicles={"V1"}, parties={"P_1"})
    # no date credit: place 0.20 + vehicle 0.25 + party 0.15 == 0.60
    assert match_score(c, a, "JHB", {"V1"}) == pytest.approx(0.60)


def test_match_score_empty_place_gives_no_place_credit():
    a = _accident(where="", vehicles=set(), parties=set())
    # place is falsy -> no 0.20 even though '' == '' ; only date 0.40
    assert match_score(_claim(), a, "", set()) == pytest.approx(0.40)


def test_match_score_no_vehicle_overlap_no_credit():
    a = _accident(where="X", vehicles={"V9"}, parties=set())
    assert match_score(_claim(), a, "", {"V1"}) == pytest.approx(0.40)


# ── resolve_accident ─────────────────────────────────────────────────────────
def test_resolve_accident_joined_by_exact_cas():
    acc = _accident(case_number="CAS100/02/2026")
    res, action = resolve_accident(_claim(case_number_raw="CAS 100/02/2026"), [acc])
    assert action == "JOINED"
    assert res is acc


def test_resolve_accident_auto_joined_when_fuzzy_at_least_085():
    # no CAS on claim; fuzzy = date .40 + place .20 + veh .25 + party .15 = 1.0 >= 0.85
    acc = _accident(case_number="CAS999/09/2020")
    res, action = resolve_accident(
        _claim(case_number_raw=None), [acc], place="JHB", vehicles={"V1"})
    assert action == "AUTO_JOINED"
    assert res is acc


def test_resolve_accident_worklist_when_between_050_and_085():
    # score = date .40 + place .20 = 0.60 (party mismatch, no vehicles) -> WORKLIST
    acc = _accident(case_number="CAS999/09/2020", parties={"P_9"})
    res, action = resolve_accident(
        _claim(case_number_raw=None, party_token="P_1"), [acc], place="JHB", vehicles=set())
    assert 0.50 <= 0.60 < 0.85
    assert action == "WORKLIST"
    # H7: a WORKLIST match is never a join — the claim anchors to its own new accident and
    # names the candidate for a human to confirm
    assert res is not acc and res.accident_id == "A_R_1"
    assert res.worklist_candidate == acc.accident_id


def test_resolve_accident_created_when_no_match_mints_a1():
    res, action = resolve_accident(
        _claim(case_number_raw=None, accident_date=date(2020, 1, 1)), [],
        place="", vehicles=set())
    assert action == "CREATED"
    assert res.accident_id == "A_R_1"            # H7: derived from the claim id, never a position
    assert res.worklist_candidate is None


def test_resolve_accident_created_id_is_independent_of_graph_size():
    # H7: two existing accidents that do not block-match -> still A_<claim_id>, so a gap in
    # the graph or two concurrent first-touch claims can never collide on an id
    old = [_accident(when=date(2000, 1, 1)), _accident(when=date(2000, 1, 1))]
    res, action = resolve_accident(
        _claim(case_number_raw=None, claim_id="R_77", accident_date=date(2020, 1, 1)), old,
        place="", vehicles=set())
    assert action == "CREATED"
    assert res.accident_id == "A_R_77"


def test_resolve_accident_created_carries_normalised_cas():
    res, action = resolve_accident(
        _claim(case_number_raw="CAS 555/01/2020", accident_date=date(2020, 1, 1)), [],
        place="", vehicles=set())
    assert action == "CREATED"
    assert res.case_number == "CAS555/01/2020"
    assert res.parties == {"P_1"}
    assert res.when == date(2020, 1, 1)


def test_resolve_accident_cas_mismatch_falls_through_to_fuzzy_then_created():
    # claim CAS does not equal accident CAS; blocking date far -> CREATED
    acc = _accident(case_number="CASOTHER", when=date(1999, 1, 1))
    res, action = resolve_accident(
        _claim(case_number_raw="CAS 100/02/2026", accident_date=date(2026, 2, 1)), [acc])
    assert action == "CREATED"


def test_resolve_accident_join_precedes_fuzzy_even_if_fuzzy_would_win():
    # exact CAS present -> JOINED regardless of fuzzy inputs
    acc = _accident(case_number="CAS100/02/2026")
    res, action = resolve_accident(
        _claim(case_number_raw="CAS 100/02/2026"), [acc], place="JHB", vehicles={"V1"})
    assert action == "JOINED"


def test_resolve_accident_keeps_best_when_later_block_match_scores_lower():
    # two accidents both block-match on date; the first scores higher (place+vehicle) and the
    # second (date only) does NOT beat it -> best stays the first. Exercises the loop-back arc
    # where `s > score` is False.
    a1 = _accident(accident_id="A1", case_number="C1", where="JHB", vehicles={"V1"}, parties=set())
    a2 = _accident(accident_id="A2", case_number="C2", where="OTHER", vehicles=set(), parties=set())
    res, action = resolve_accident(
        _claim(case_number_raw=None, party_token="PX"), [a1, a2], place="JHB", vehicles={"V1"})
    # a1 score = date .40 + place .20 + vehicle .25 = 0.85 -> AUTO_JOINED; a2's 0.40 never wins
    assert res.accident_id == "A1" and action == "AUTO_JOINED"


def test_resolve_accident_thresholds_constants():
    assert (AUTO_JOIN, WORKLIST) == (0.85, 0.50)
