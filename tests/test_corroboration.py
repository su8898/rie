"""Per-function unit tests for engine.corroboration — concrete value assertions.

MAX_CONVERGENCE = sum of SOURCE_WEIGHT values:
  SAPS 0.5 + EMS 2.0 + HOSPITAL 2.0 + PREAUTH_L3 2.0 + PHARMACY 1.0
  + INDEPENDENT_CLAIMANT 2.0 + EMPLOYER 1.0 + INJURY_COHERENCE 1.5 = 12.0
convergence = round(100 * total / 12.0, 1).
"""
from __future__ import annotations

import pytest

from engine.corroboration import MAX_CONVERGENCE, SOURCE_WEIGHT, convergence, corroboration_signals
from engine.models import Accident


def _accident(**over) -> Accident:
    base = dict(
        accident_id="A", case_number="C", when=None, where="", vehicles=set(),
        parties={"P_1"}, oar_occupants=None, sources={},
    )
    base.update(over)
    return Accident(**base)


# ── convergence ──────────────────────────────────────────────────────────────
def test_max_convergence_is_twelve():
    assert MAX_CONVERGENCE == 12.0


def test_convergence_empty_sources_is_zero():
    assert convergence(_accident(sources={})) == 0.0


def test_convergence_single_saps():
    # 0.5 / 12 * 100 == 4.1666.. -> 4.2
    assert convergence(_accident(sources={"SAPS": "c1"})) == 4.2


def test_convergence_three_independent_sources():
    # EMS 2.0 + HOSPITAL 2.0 + SAPS 0.5 = 4.5 -> 4.5/12*100 == 37.5
    a = _accident(sources={"EMS": "c1", "HOSPITAL": "c2", "SAPS": "c3"})
    assert convergence(a) == 37.5


def test_convergence_all_sources_is_one_hundred():
    a = _accident(sources={k: f"c{i}" for i, k in enumerate(SOURCE_WEIGHT)})
    assert convergence(a) == 100.0


def test_convergence_cluster_collapse_two_classes_one_cluster_count_once():
    # EMS(ring1) + HOSPITAL(ring1) collapse to a single vote (2.0) + INDEPENDENT_CLAIMANT(c9)=2.0
    # total 4.0 -> 4.0/12*100 == 33.333 -> 33.3
    a = _accident(sources={"EMS": "ring1", "HOSPITAL": "ring1", "INDEPENDENT_CLAIMANT": "c9"})
    assert convergence(a) == 33.3


def test_convergence_same_class_same_cluster_still_counts_once():
    # dict can't repeat keys, but a class re-seen with its own cluster still counts once;
    # here EMS + PHARMACY share 'x': second one (PHARMACY) collapses.
    # EMS(x)=2.0 counted; PHARMACY(x) collapses. total 2.0 -> 2/12*100 == 16.666 -> 16.7
    a = _accident(sources={"EMS": "x", "PHARMACY": "x"})
    assert convergence(a) == 16.7


def test_convergence_unknown_source_class_defaults_to_half():
    # 'MYSTERY' not in SOURCE_WEIGHT -> default 0.5 -> 0.5/12*100 == 4.2
    a = _accident(sources={"MYSTERY": "c1"})
    assert convergence(a) == 4.2


def test_convergence_two_classes_distinct_clusters_no_collapse():
    # EMS(a)=2.0 + HOSPITAL(b)=2.0 = 4.0 -> 33.3
    a = _accident(sources={"EMS": "a", "HOSPITAL": "b"})
    assert convergence(a) == 33.3


# ── corroboration_signals ────────────────────────────────────────────────────
def _high_conv_sources():
    # EMS+HOSPITAL+SAPS -> 37.5, comfortably above a floor of 20
    return {"EMS": "c1", "HOSPITAL": "c2", "SAPS": "c3"}


def test_signals_claimant_surge_when_parties_exceed_oar_and_not_bus_taxi():
    a = _accident(parties={"P_1", "P_2"}, oar_occupants=1, sources=_high_conv_sources())
    assert corroboration_signals(a, cohort_is_bus_taxi=False, conv_floor_p10=20.0) == ["CLAIMANT_SURGE"]


def test_signals_surge_suppressed_when_cohort_is_bus_taxi():
    a = _accident(parties={"P_1", "P_2"}, oar_occupants=1, sources=_high_conv_sources())
    assert corroboration_signals(a, cohort_is_bus_taxi=True, conv_floor_p10=20.0) == []


def test_signals_no_surge_when_parties_not_greater_than_oar():
    a = _accident(parties={"P_1"}, oar_occupants=5, sources=_high_conv_sources())
    assert corroboration_signals(a, cohort_is_bus_taxi=False, conv_floor_p10=20.0) == []


def test_signals_no_surge_when_oar_is_none():
    # oar_occupants None is falsy -> guard short-circuits, no surge
    a = _accident(parties={"P_1", "P_2"}, oar_occupants=None, sources=_high_conv_sources())
    assert corroboration_signals(a, cohort_is_bus_taxi=False, conv_floor_p10=20.0) == []


def test_signals_convergence_thin_below_floor():
    # SAPS only -> convergence 4.2 < floor 20 -> CONVERGENCE_THIN (parties<=oar so no surge)
    a = _accident(parties={"P_1"}, oar_occupants=5, sources={"SAPS": "c1"})
    assert corroboration_signals(a, cohort_is_bus_taxi=False, conv_floor_p10=20.0) == ["CONVERGENCE_THIN"]


def test_signals_not_thin_at_or_above_floor():
    # convergence exactly at floor is NOT thin (strict <). Pick sources giving 37.5 with floor 37.5
    a = _accident(parties={"P_1"}, oar_occupants=5, sources=_high_conv_sources())
    assert corroboration_signals(a, cohort_is_bus_taxi=False, conv_floor_p10=37.5) == []


def test_signals_both_surge_and_thin():
    # SAPS only -> thin; parties 2 > oar 1 and not bus/taxi -> surge. Order: surge then thin.
    a = _accident(parties={"P_1", "P_2"}, oar_occupants=1, sources={"SAPS": "c1"})
    assert corroboration_signals(a, cohort_is_bus_taxi=False, conv_floor_p10=20.0) == \
        ["CLAIMANT_SURGE", "CONVERGENCE_THIN"]


def test_signals_neither_when_high_conv_and_no_surge():
    a = _accident(parties={"P_1"}, oar_occupants=5, sources=_high_conv_sources())
    assert corroboration_signals(a, cohort_is_bus_taxi=False, conv_floor_p10=20.0) == []
