"""Comparable-awards store — CPI-adjusted band computation + small-n guard (domain-logic §5d).

The band is COMPUTED (inflation-adjusted p25–p75), never hand-set; a class with < MIN_ROBUST
authorities is shown individually with no band.
"""
from __future__ import annotations

from server.db import Base, SessionLocal, engine
from server.seed import seed

Base.metadata.create_all(engine)                        # ensure the new ref tables exist + seed them
with SessionLocal() as _s:
    seed(_s)

from server import awards_service  # noqa: E402


def _band(injury_class, severity=None):
    with SessionLocal() as db:
        return awards_service.award_band(db, injury_class, severity)


def test_robust_class_gets_p25_p75_band():
    r = _band("TBI", "SEVERE")
    assert r["n"] == 6 and r["robust"] is True
    assert r["band_p25"] < r["band_median"] < r["band_p75"]
    assert r["band_min"] <= r["band_p25"] and r["band_p75"] <= r["band_max"]


def test_awards_are_inflation_adjusted_to_current_rand():
    r = _band("TBI", "SEVERE")                          # current year 2026 -> CPI 180
    a2012 = next(a for a in r["awards"] if a["award_year"] == 2012)   # 1.4M at CPI 89
    assert a2012["adjusted"] == round(1_400_000 * 180.0 / 89.0, 2)
    assert all(a["adjusted"] >= a["award_rand"] for a in r["awards"])  # inflation only raises


def test_small_n_guard_shows_individual_awards_no_band():
    r = _band("AMPUTATION_LOWER_LIMB", "SEVERE")
    assert r["n"] == 3 and r["robust"] is False
    assert "band_p25" not in r and "band_p75" not in r  # < 5 authorities -> no computed band
    assert len(r["awards"]) == 3                        # shown individually
    assert "band_min" in r and "band_max" in r          # envelope still available


def test_band_for_offer_p25_p75_when_robust_else_envelope():
    robust = _band("PARAPLEGIA", "SEVERE")
    assert awards_service.band_for_offer(robust) == (robust["band_p25"], robust["band_p75"])
    small = _band("FACIAL_DISFIGUREMENT", "MODERATE")
    assert awards_service.band_for_offer(small) == (small["band_min"], small["band_max"])


def test_unknown_class_is_empty():
    r = _band("NO_SUCH_INJURY")
    assert r["n"] == 0 and r["robust"] is False and r["awards"] == [] and "band_min" not in r


def test_no_cpi_falls_back_to_nominal():
    # _inflate with an empty CPI map returns the nominal amount (never crashes)
    assert awards_service._inflate(500_000.0, 2015, {}, 2026) == 500_000.0


def test_injury_classes_lists_severity_tiers():
    with SessionLocal() as db:
        classes = awards_service.injury_classes(db)
    tbi = next(c for c in classes if c["injury_class"] == "TBI")
    assert set(tbi["severity_tiers"]) == {"SEVERE", "MODERATE"}
