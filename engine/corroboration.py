"""Corroboration — convergence as proof (domain-logic §6.0).

A real accident leaves a constellation of independent traces that agree without coordinating.
Convergence = independence-weighted agreement across source classes; sources sharing one
party-cluster (same attorney/provider network) collapse to a single vote.
"""
from __future__ import annotations

from .models import Accident

SOURCE_WEIGHT = {  # independence-weighted source classes
    "SAPS": 0.5, "EMS": 2.0, "HOSPITAL": 2.0, "PREAUTH_L3": 2.0,
    "PHARMACY": 1.0, "INDEPENDENT_CLAIMANT": 2.0, "EMPLOYER": 1.0, "INJURY_COHERENCE": 1.5,
}
MAX_CONVERGENCE = sum(SOURCE_WEIGHT.values())


def convergence(a: Accident) -> float:
    """0-100. Sources sharing one party-cluster collapse to a single vote."""
    seen_clusters: dict[str, str] = {}
    total = 0.0
    for source_class, cluster in a.sources.items():
        if cluster in seen_clusters and seen_clusters[cluster] != source_class:
            continue                                  # same attorney/provider network: one vote
        seen_clusters[cluster] = source_class
        total += SOURCE_WEIGHT.get(source_class, 0.5)
    return round(100 * total / MAX_CONVERGENCE, 1)


def corroboration_signals(a: Accident, cohort_is_bus_taxi: bool, conv_floor_p10: float) -> list[str]:
    out = []
    if a.oar_occupants and len(a.parties) > a.oar_occupants and not cohort_is_bus_taxi:
        out.append("CLAIMANT_SURGE")                  # cohort-aware; OAR count = LOW confidence
    if convergence(a) < conv_floor_p10:               # calibrated from the genuine-accident band
        out.append("CONVERGENCE_THIN")
    return out
