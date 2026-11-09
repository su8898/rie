"""Accident entity resolution (domain-logic §6.0).

Claims join the right accident via normalised case number (exact) or blocking + fuzzy match
(date +/-1 day, place, vehicles, party). Above AUTO_JOIN -> auto-join; above WORKLIST -> human
worklist; else a new accident is materialised on first touch.
"""
from __future__ import annotations

from typing import Optional

from .models import Accident, Claim

AUTO_JOIN, WORKLIST = 0.85, 0.50


def normalise_cas(raw: Optional[str]) -> Optional[str]:
    """CAS 123/04/2026 · 123/4/26 · cas123-4-2026 -> 'CAS123/04/2026'."""
    if not raw:
        return None
    digits = [t for t in "".join(c if c.isdigit() else " " for c in raw).split() if t]
    if len(digits) < 3:
        return None
    n, m, y = digits[0], digits[1].zfill(2), digits[2]
    y = ("20" + y) if len(y) == 2 else y
    return f"CAS{int(n)}/{m}/{y}"


def match_score(c: Claim, a: Accident, place: str, vehicles: set[str]) -> float:
    s = 0.0
    s += 0.40 if abs((c.accident_date - a.when).days) <= 1 else 0.0
    s += 0.20 if place and place == a.where else 0.0
    s += 0.25 if vehicles & a.vehicles else 0.0
    s += 0.15 if c.party_token in a.parties else 0.0
    return s


def resolve_accident(c: Claim, accidents: list[Accident],
                     place: str = "", vehicles: set[str] = frozenset()) -> tuple[Accident, str]:
    """Returns (accident, action) — action in JOINED | AUTO_JOINED | WORKLIST | CREATED.
    A WORKLIST match is NOT a join: the claim anchors to its own new accident, which names the
    candidate (`worklist_candidate`) for a human to confirm or dismiss. New accident ids derive
    from the first-touch claim id — unique by construction, never a position in the graph."""
    cas = normalise_cas(c.case_number_raw)
    if cas:
        for a in accidents:
            if a.case_number == cas:
                return a, "JOINED"
    best, score = None, 0.0
    for a in accidents:                              # blocking: date +/- 1 day
        if abs((c.accident_date - a.when).days) <= 1:
            s = match_score(c, a, place, vehicles)
            if s > score:
                best, score = a, s
    if best and score >= AUTO_JOIN:
        return best, "AUTO_JOINED"
    a = Accident(f"A_{c.claim_id}", cas, c.accident_date, place, set(vehicles),
                 {c.party_token}, None)              # materialised on first touch
    if best and score >= WORKLIST:
        a.worklist_candidate = best.accident_id      # human confirms the join (or not)
        return a, "WORKLIST"
    return a, "CREATED"
