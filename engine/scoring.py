"""Scoring — reasons -> points -> band (domain-logic §10, §11).

Hard fraud grounds band RED directly. Soft SCORED features add points; endogenous points are
capped below RED (endogenous signals alone never reach RED). SHADOW signals are computed and
stored but contribute zero points and stay invisible.
"""
from __future__ import annotations

from typing import Optional

from .models import Assessment
from .reasons import MODE, R
from .vocab import (
    AMBER_AT, Band, Category, ENDOGENOUS_POINT_CAP, Maturity, RED_AT, ReasonMeta, SignalMode,
)


def effective_mode(code: str, meta: Optional[ReasonMeta], overrides: dict) -> SignalMode:
    """§11 — the live mode: the ADMIN override when it is a real SignalMode and the signal is
    not Grounded (law-cited gates are always SCORED), else the launch default."""
    ov = overrides.get(code)
    if isinstance(ov, SignalMode) and meta is not None and meta.maturity is not Maturity.GROUNDED:
        return ov
    return MODE.get(code, SignalMode.SCORED)


def score_and_band(all_reasons: list[str], mode_overrides: Optional[dict] = None) -> Assessment:
    ov = mode_overrides or {}                         # §11 — ADMIN signal-mode overrides (reference data)
    visible, advisory, shadow, pts, endo_pts = [], [], [], 0, 0
    for code in dict.fromkeys(all_reasons):           # dedupe, keep order
        meta = R.get(code)
        if meta is None:
            visible.append(code); continue
        mode = effective_mode(code, meta, ov)
        if mode is SignalMode.SHADOW:
            shadow.append(code); continue
        visible.append(code)
        if mode is SignalMode.ADVISORY:
            advisory.append(code)                     # visible, zero points, no say in the disposition
        if mode is SignalMode.SCORED and not meta.hard:
            if meta.endogenous:
                endo_pts += meta.points               # capped: endogenous alone never reaches RED
            else:
                pts += meta.points
        if meta.hard and meta.category in (Category.FRAUD,):
            pts += 50                                 # hard fraud grounds band RED directly
    score = pts + min(endo_pts, ENDOGENOUS_POINT_CAP)
    band = Band.RED if score >= RED_AT else Band.AMBER if score >= AMBER_AT else Band.GREEN
    return Assessment(visible, shadow, score, band, advisory=advisory)
