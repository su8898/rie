"""Heads of damage — gross -> apportioned -> capped -> offer (domain-logic §5).

Each head is a small engine. Past medical sums payable lines; loss of earnings / support cap each
year at the accident-date cap THEN apportion (Sweatman); general damages is gated by the SI
process; funeral pays actual necessary costs. All six heads: past/future medical, loss of
earnings, loss of support, general damages, funeral.
"""
from __future__ import annotations

from typing import Optional

from .models import Claim, LineResult, Ruleset
from .vocab import D, money


def apportion(amount, fault_pct: Optional[float]) -> float:
    return money(D(amount) * (1 - D(fault_pct or 0.0) / 100))


def head_past_medical(line_results: list[LineResult], fault_pct: Optional[float]) -> float:
    return apportion(sum(D(r.payable) for r in line_results), fault_pct)


def _sweatman(annual_losses_after_contingency: list[float], c: Claim, rs: Ruleset
              ) -> tuple[float, list[dict]]:
    """§5c cap engine (s17(4)(c)) — cap each year at the accident-date cap, THEN apportion.
    Shared by loss of earnings and loss of support; the worksheet is stored for litigation."""
    cap = rs.cap_at(c.accident_date)
    worksheet = [{"year": i + 1, "loss": loss, "cap": cap, "capped": min(loss, cap)}
                 for i, loss in enumerate(annual_losses_after_contingency)]
    return apportion(sum(D(w["capped"]) for w in worksheet), c.fault_pct), worksheet


def head_loss_of_earnings(annual_losses_after_contingency: list[float],
                          c: Claim, rs: Ruleset) -> tuple[float, list[dict]]:
    """§5c — loss of earnings: Sweatman year-by-year cap, THEN apportion."""
    return _sweatman(annual_losses_after_contingency, c, rs)


def head_loss_of_support(annual_support_losses_after_contingency: list[float],
                         c: Claim, rs: Ruleset) -> tuple[float, list[dict]]:
    """§5c — dependants' loss of support (deceased breadwinner). s17(4)(c) caps 'loss of income
    OR support', so this is the SAME Sweatman cap engine as loss of earnings."""
    return _sweatman(annual_support_losses_after_contingency, c, rs)


def head_general_damages(c: Claim, band_p25: float, band_p75: float,
                         proposed: float) -> tuple[float, list[str]]:
    """§5d — gated by SI (list-first -> WPI >= 30% -> narrative, decided in §8b machinery)."""
    if not c.si_accepted:
        return 0.0, ["GENERAL_DAMAGES_NO_SI"]
    reasons = [] if band_p25 <= proposed <= band_p75 else ["GD_OUTSIDE_BAND_NOTE"]  # note, never a gate
    return apportion(proposed, c.fault_pct), reasons


def head_funeral(c: Claim, necessary_costs: float, non_necessary: float = 0.0
                 ) -> tuple[float, list[str]]:
    """§5e — actual, necessary cremation/burial costs (invoice-proven), apportioned. FUNERAL_SCOPE
    flags any non-necessary components (soft -> routes to review, never a hard exclusion)."""
    reasons = ["FUNERAL_SCOPE"] if non_necessary > 0 else []
    return apportion(necessary_costs, c.fault_pct), reasons
