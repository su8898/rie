"""Pure party-scoring unit tests — the composite formula, n-guard, rating bands, percentile."""
from __future__ import annotations

from server.party_scoring import MIN_ROBUST, PartyStats, party_risk, percentile, rating


def test_percentile_midrank():
    assert percentile([], 5) == 0.0
    assert percentile([1, 2, 3, 4], 3) == 62.5        # 2 below + 0.5*1 equal / 4
    assert percentile([5, 5, 5], 5) == 50.0           # all equal -> midrank 50
    assert percentile([1, 2, 3], 100) == 100.0


def test_rating_bands():
    assert rating(75) == "CRITICAL"
    assert rating(74.9) == "HIGH"
    assert rating(55) == "HIGH"
    assert rating(35) == "ELEVATED"
    assert rating(18) == "WATCH"
    assert rating(17.9) == "LOW"


def test_n_guard_suppresses_score():
    s = PartyStats(n_claims=MIN_ROBUST - 1, red_rate=100, amber_rate=0, avg_score=40,
                   util_rate=100, value_p=100)
    r = party_risk(s)
    assert r["score"] == 0.0 and r["rating"] == "LOW" and r["confidence"] == "LOW_N"


def test_composite_score():
    s = PartyStats(n_claims=10, red_rate=20, amber_rate=10, avg_score=30, util_rate=15, value_p=90)
    r = party_risk(s)
    # behavioural = 20*1.5 + 10*0.4 + min(30,40) = 64 ; cohort = (90-75)*4 = 60 ;
    # over_servicing = 15*4 = 60 ; history = 0 -> 0.4*64 + 0.2*60 + 0.2*60 + 0.2*0 = 49.6
    assert r["components"] == {"behavioural": 64.0, "cohort_outlier": 60.0,
                               "over_servicing": 60.0, "history": 0.0}
    assert r["score"] == 49.6 and r["rating"] == "ELEVATED" and r["confidence"] == "OK"


def test_components_capped_at_100():
    s = PartyStats(n_claims=10, red_rate=100, amber_rate=100, avg_score=100, util_rate=100,
                   value_p=100, afterhours_p=100, clawback_rate=100, n_open_cases=10)
    r = party_risk(s)
    assert all(v == 100.0 for v in r["components"].values())
    assert r["score"] == 100.0 and r["rating"] == "CRITICAL"


def test_pricing_excluded_is_structural():
    # a party whose only signal is over-pricing / duplicates (ADJUSTED, not fraud) scores clean:
    # util_rate counts only fraud-category reasons, so a pricing-only party has util_rate 0.
    s = PartyStats(n_claims=20, red_rate=0, amber_rate=0, avg_score=0, util_rate=0, value_p=50)
    r = party_risk(s)
    assert r["score"] == 0.0 and r["rating"] == "LOW"
