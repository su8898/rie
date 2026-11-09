"""Disposition — one shared worst-wins ordering (domain-logic §9).

Enum order = precedence: FRAUD > MERITS > COMPLIANCE > PREAUTH > SI_GATE > REVIEW > ADJUSTED > CLEAN.
Only dispositive reasons route (hard gates, zero-point facts, heuristics at AMBER+); ADVISORY never.
"""
from __future__ import annotations

from .models import Assessment
from .reasons import R
from .vocab import Band, Category


def dispositive(code: str, assessment: Assessment) -> bool:
    """§9/§11 — what may route a claim: hard gates and zero-point facts (a repricing) always;
    a scoring heuristic only through its band (never alone below AMBER — statistical signals
    never auto-reject); an ADVISORY signal never."""
    meta = R.get(code)
    if meta is None or code in assessment.advisory:
        return False
    return meta.hard or meta.points == 0 or assessment.band is not Band.GREEN


def disposition(assessment: Assessment, merits_pending: bool) -> Category:
    cats = {R[c].category for c in assessment.reasons if dispositive(c, assessment)}
    if merits_pending:
        cats.add(Category.MERITS)                     # held_for_merits
    for cat in Category:                              # enum order = precedence
        if cat in cats:
            return cat
    return Category.CLEAN
