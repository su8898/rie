"""Comparable-awards store — general-damages quantum guidance (domain-logic §5d).

Bands are COMPUTED, not hand-set: each authority's award is inflation-adjusted to current rand via
the CPI index, then the band is the adjusted p25–p75 (with min/max shown). Small-n guard: an
injury class / severity tier with < MIN_ROBUST authorities is shown as individual awards, never a
band. Bands are ENDOGENOUS-equivalent — guidance only, never an auto-computed offer; the offer
builder feeds the band to head_general_damages purely to raise the GD_OUTSIDE_BAND_NOTE.
"""
from __future__ import annotations

import statistics
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models

MIN_ROBUST = 5                                          # < 5 authorities -> individual, no band (§5d)


def _cpi(db: Session) -> dict[int, float]:
    return {r.year: r.index for r in db.scalars(select(models.RefCpi))}


def _inflate(amount: float, from_year: int, cpi: dict[int, float], current_year: int) -> float:
    """Adjust an award-year rand amount to current rand via the CPI index (nearest year if a gap)."""
    if not cpi:
        return round(amount, 2)                         # no CPI loaded -> nominal
    fi = cpi.get(from_year) or cpi[min(cpi, key=lambda y: abs(y - from_year))]
    ci = cpi.get(current_year) or cpi[max(cpi)]
    return round(amount * ci / fi, 2)


def award_band(db: Session, injury_class: str, severity_tier: Optional[str] = None,
               current_year: Optional[int] = None) -> dict:
    stmt = select(models.RefComparableAward).where(
        models.RefComparableAward.injury_class == injury_class)
    if severity_tier:
        stmt = stmt.where(models.RefComparableAward.severity_tier == severity_tier)
    rows = list(db.scalars(stmt.order_by(models.RefComparableAward.award_rand)))

    cpi = _cpi(db)
    cur = current_year or (max(cpi) if cpi else 2026)
    awards = [{"citation": a.citation, "court": a.court, "severity_tier": a.severity_tier,
               "award_year": a.award_date.year, "award_rand": a.award_rand,
               "adjusted": _inflate(a.award_rand, a.award_date.year, cpi, cur), "notes": a.notes}
              for a in rows]
    adjusted = sorted(a["adjusted"] for a in awards)
    n = len(adjusted)
    out: dict = {"injury_class": injury_class, "severity_tier": severity_tier, "n": n,
                 "robust": n >= MIN_ROBUST, "current_year": cur, "awards": awards}
    if n:
        out["band_min"], out["band_max"] = adjusted[0], adjusted[-1]
    if n >= MIN_ROBUST:                                 # p25–p75 band only when robust (§5d small-n guard)
        p25, median, p75 = statistics.quantiles(adjusted, n=4, method="inclusive")
        out.update(band_p25=round(p25, 2), band_median=round(median, 2), band_p75=round(p75, 2))
    return out


def band_for_offer(res: dict) -> tuple[float, float]:
    """(low, high) to feed head_general_damages — the p25–p75 band when robust, else the
    min–max envelope of the individual awards (still guidance, small-n honest)."""
    lo = res.get("band_p25", res.get("band_min", 0.0))
    hi = res.get("band_p75", res.get("band_max", 0.0))
    return lo, hi


def injury_classes(db: Session) -> list[dict]:
    """Distinct injury classes + severity tiers present (for the offer-builder pickers)."""
    rows = db.execute(
        select(models.RefComparableAward.injury_class, models.RefComparableAward.severity_tier)
        .distinct().order_by(models.RefComparableAward.injury_class,
                             models.RefComparableAward.severity_tier)).all()
    out: dict[str, list[str]] = {}
    for injury_class, tier in rows:
        out.setdefault(injury_class, []).append(tier)
    return [{"injury_class": k, "severity_tiers": v} for k, v in out.items()]
