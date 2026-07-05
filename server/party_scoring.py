"""Party risk scoring — pure, deterministic (domain-logic §7).

Composite 0-100 score from four weighted components (the CIE pattern), cohort-relative so
legitimate archetypes are not false-flagged, n-guarded below MIN_ROBUST, and with pricing +
duplicate billing deliberately EXCLUDED (they are resolved at adjudication, not fraud). Some
component inputs (after-hours, clawback, open cases) are dormant until those feeds/modules land;
the formula carries them so the score enriches without a rewrite.
"""
from __future__ import annotations

from dataclasses import dataclass

MIN_ROBUST = 5                       # n-guard: fewer claims than this -> low confidence, no score
WEIGHTS = {"behavioural": 0.40, "cohort_outlier": 0.20, "over_servicing": 0.20, "history": 0.20}


@dataclass
class PartyStats:
    n_claims: int
    red_rate: float                  # % of the party's claims banded RED
    amber_rate: float                # % AMBER
    avg_score: float                 # mean engine score across the party's claims
    util_rate: float                 # % of claims flagged with a non-pricing fraud reason
    value_p: float                   # WITHIN-COHORT value percentile (0-100) — the outlier control
    afterhours_p: float = 0.0        # dormant until a place-of-service feed exists
    clawback_rate: float = 0.0       # dormant until the recovery module exists
    n_open_cases: int = 0            # dormant until the case module exists


def _behavioural(s: PartyStats) -> float:
    return min(100.0, s.red_rate * 1.5 + s.amber_rate * 0.4 + min(s.avg_score, 40.0))


def _cohort_outlier(s: PartyStats) -> float:
    return min(100.0, max(0.0, s.value_p - 75.0) * 4.0 + max(0.0, s.afterhours_p - 80.0) * 2.0)


def _over_servicing(s: PartyStats) -> float:
    return min(100.0, s.util_rate * 4.0)


def _history(s: PartyStats) -> float:
    return min(100.0, s.clawback_rate * 8.0 + s.n_open_cases * 20.0)


def rating(score: float) -> str:
    if score >= 75:
        return "CRITICAL"
    if score >= 55:
        return "HIGH"
    if score >= 35:
        return "ELEVATED"
    if score >= 18:
        return "WATCH"
    return "LOW"


def party_risk(s: PartyStats) -> dict:
    """0-100 composite + rating + component breakdown. Below MIN_ROBUST claims -> LOW confidence."""
    components = {
        "behavioural": round(_behavioural(s), 1),
        "cohort_outlier": round(_cohort_outlier(s), 1),
        "over_servicing": round(_over_servicing(s), 1),
        "history": round(_history(s), 1),
    }
    if s.n_claims < MIN_ROBUST:
        return {"score": 0.0, "rating": "LOW", "confidence": "LOW_N",
                "components": components, "n_claims": s.n_claims}
    score = round(sum(WEIGHTS[k] * components[k] for k in WEIGHTS), 1)
    return {"score": score, "rating": rating(score), "confidence": "OK",
            "components": components, "n_claims": s.n_claims}


def percentile(values: list[float], x: float) -> float:
    """Midrank percentile of x within values (0-100)."""
    if not values:
        return 0.0
    below = sum(1 for v in values if v < x)
    equal = sum(1 for v in values if v == x)
    return round(100.0 * (below + 0.5 * equal) / len(values), 1)
