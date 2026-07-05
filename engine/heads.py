"""Heads of damage — gross -> apportioned -> capped -> offer (domain-logic §5).

Each head is a small engine. Past medical sums payable lines; loss-of-earnings caps each year
at the accident-date cap THEN apportions (Sweatman); general damages is gated by the SI process.
"""
from __future__ import annotations

from typing import Optional

from .models import Claim, LineResult, Ruleset


def apportion(amount: float, fault_pct: Optional[float]) -> float:
    return round(amount * (1 - (fault_pct or 0.0) / 100), 2)


def head_past_medical(line_results: list[LineResult], fault_pct: Optional[float]) -> float:
    return apportion(sum(r.payable for r in line_results), fault_pct)


def head_loss_of_earnings(annual_losses_after_contingency: list[float],
                          c: Claim, rs: Ruleset) -> tuple[float, list[dict]]:
    """§5c — Sweatman: cap each year at the accident-date cap, THEN apportion."""
    cap = rs.cap_at(c.accident_date)
    worksheet = [{"year": i + 1, "loss": loss, "cap": cap, "capped": min(loss, cap)}
                 for i, loss in enumerate(annual_losses_after_contingency)]
    total = apportion(sum(w["capped"] for w in worksheet), c.fault_pct)
    return total, worksheet                           # worksheet stored — litigation-reproducible


def head_general_damages(c: Claim, band_p25: float, band_p75: float,
                         proposed: float) -> tuple[float, list[str]]:
    """§5d — gated by SI (list-first -> WPI >= 30% -> narrative, decided in §8b machinery)."""
    if not c.si_accepted:
        return 0.0, ["GENERAL_DAMAGES_NO_SI"]
    reasons = [] if band_p25 <= proposed <= band_p75 else ["GD_OUTSIDE_BAND_NOTE"]  # note, never a gate
    return apportion(proposed, c.fault_pct), reasons
