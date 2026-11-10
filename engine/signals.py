"""Billing signals — encounter-shaped over-servicing screens (domain-logic §10).

Soft features only: they score, they never reprice a line. An encounter is one provider
treating the claimant on one day. Thresholds live on the Ruleset (calibration is governance).
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from .models import Activity, Claim, Line, Ruleset


def iso_week(d: date) -> date:
    """The Monday of the date's ISO week."""
    return d - timedelta(days=d.weekday())


def padded(lines: list[Line], rs: Ruleset) -> bool:
    """Consumable stacking: many NAPPI lines forming most of one encounter."""
    n = sum(1 for l in lines if l.kind == "NAPPI")
    return n >= rs.material_lines_flag and n >= rs.material_share * len(lines)


def billing_signals(c: Claim, rs: Ruleset, tier: str, activity: Optional[Activity] = None) -> list[str]:
    """`activity` is the same claimant's and the same providers' billing on OTHER claims;
    without it the screens see this claim alone."""
    act = activity or Activity()
    out: list[str] = []
    encounters: dict[tuple[str, date], list[Line]] = {}
    for l in c.lines:
        encounters.setdefault((l.provider_id, l.service_date), []).append(l)
    if any(len(ls) >= rs.line_count_flag for ls in encounters.values()):
        out.append("LINE_COUNT_OUTLIER")
    if any(padded(ls, rs) for ls in encounters.values()):
        out.append("MATERIAL_PADDING")
    if not c.facility:                                # a hospital bills many patients, and daily care, legitimately
        if any(act.provider_day.get(e, 0) + 1 >= rs.impossible_day_encounters for e in encounters):
            out.append("IMPOSSIBLE_DAY")              # one provider, one day, too many claimants
        weeks: dict[date, int] = {}
        for _provider, day in set(encounters) | act.claimant_encounters:
            weeks[iso_week(day)] = weeks.get(iso_week(day), 0) + 1
        if any(weeks[iso_week(day)] >= rs.impossible_week_encounters for _provider, day in encounters):
            out.append("IMPOSSIBLE_WEEK")             # one claimant, one week, more than a visit a day
    providers = {d: set(ps) for d, ps in act.claimant_providers.items()}
    for l in c.lines:
        providers.setdefault(l.discipline or tier, set()).add(l.provider_id)
    if any(len(providers[d]) >= rs.shopping_providers
           for d in {l.discipline or tier for l in c.lines} - rs.no_agency_disciplines):
        out.append("PROVIDER_SHOPPING")               # substitutable providers on one claimant
    return out
