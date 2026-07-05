"""Scoring — reasons -> points -> band (domain-logic §10, §11).

Hard fraud grounds band RED directly. Soft SCORED features add points; endogenous points are
capped below RED (endogenous signals alone never reach RED). SHADOW signals are computed and
stored but contribute zero points and stay invisible.
"""
from __future__ import annotations

from .models import Assessment
from .reasons import MODE, R
from .vocab import (
    AMBER_AT, Band, Category, ENDOGENOUS_POINT_CAP, RED_AT, SignalMode,
)


def score_and_band(all_reasons: list[str]) -> Assessment:
    visible, shadow, pts, endo_pts = [], [], 0, 0
    for code in dict.fromkeys(all_reasons):           # dedupe, keep order
        meta, mode = R.get(code), MODE.get(code, SignalMode.SCORED)
        if meta is None:
            visible.append(code); continue
        if mode is SignalMode.SHADOW:
            shadow.append(code); continue
        visible.append(code)
        if mode is SignalMode.SCORED and not meta.hard:
            if meta.endogenous:
                endo_pts += meta.points               # capped: endogenous alone never reaches RED
            else:
                pts += meta.points
        if meta.hard and meta.category in (Category.FRAUD,):
            pts += 50                                 # hard fraud grounds band RED directly
    score = pts + min(endo_pts, ENDOGENOUS_POINT_CAP)
    band = Band.RED if score >= RED_AT else Band.AMBER if score >= AMBER_AT else Band.GREEN
    return Assessment(visible, shadow, score, band)
