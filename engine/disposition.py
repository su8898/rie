"""Disposition — one shared worst-wins ordering (domain-logic §9).

Enum order = precedence: FRAUD > MERITS > COMPLIANCE > PREAUTH > SI_GATE > ADJUSTED > CLEAN.
"""
from __future__ import annotations

from .models import Assessment
from .reasons import R
from .vocab import Category


def disposition(assessment: Assessment, merits_pending: bool) -> Category:
    cats = {R[c].category for c in assessment.reasons if c in R}
    if merits_pending:
        cats.add(Category.MERITS)                     # held_for_merits
    for cat in Category:                              # enum order = precedence
        if cat in cats:
            return cat
    return Category.CLEAN
