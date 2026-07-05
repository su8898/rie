"""Line adjudication — reconcile, reprice, or refer (domain-logic §3, §5f).

Hard causation/date gates, then undertaking + pre-authorisation reconciliation, then reference
pricing (the payment rule: pay min(billed, reference) on ENFORCEABLE/ACCEPTED; signal only on
INTERDICTED/ENDOGENOUS).
"""
from __future__ import annotations

from typing import Optional

from .models import Authorisation, Claim, Line, LineResult, Ruleset, Undertaking
from .reference import RefBook, resolve
from .vocab import PAYMENT_RULE_STATUSES


def find_authorisation(u: Optional[Undertaking], line: Line) -> Optional[Authorisation]:
    if not u:
        return None
    for auth in u.authorisations:
        if auth.status == "APPROVED" and line.code in auth.codes \
           and auth.valid_from <= line.service_date <= auth.valid_to:
            return auth
    return None


def adjudicate_line(c: Claim, line: Line, book: RefBook, rs: Ruleset,
                    tier: str, seen: set, accident_dx_regions: set[str]) -> LineResult:
    reasons: list[str] = []

    # hard causation/date gates (§4d)
    if line.service_date < c.accident_date:
        return LineResult(0.0, ["SERVICE_BEFORE_ACCIDENT"], "—")
    key = (c.party_token, line.provider_id, line.service_date, line.code, line.amount)
    if key in seen:                                   # §4e/§4f — pay once, across claim types
        return LineResult(0.0, ["DUPLICATE_LINE"], "—")
    seen.add(key)
    if line.dx[:3] not in accident_dx_regions and accident_dx_regions:
        reasons.append("DX_ACCIDENT_MISMATCH")        # soft -> review, aggravation compensable

    # undertaking + pre-authorisation reconciliation (§5b, §5f)
    if c.claim_type == "UNDERTAKING_INVOICE":
        u = c.undertaking
        if not u or not u.active:
            return LineResult(0.0, ["UNDERTAKING_NOT_ACTIVE"], "—")
        in_scope = line.dx[:3] in {d[:3] for d in u.scope_dx}
        if not in_scope:
            if u.scope_coded:
                return LineResult(0.0, ["UNDERTAKING_SCOPE"], "—")
            reasons.append("UNDERTAKING_SCOPE")       # soft on uncoded legacy scope -> review
        auth = find_authorisation(u, line)
        if auth:                                      # the promise priced in advance
            ceiling = min(auth.ceiling, auth.qty_limit and auth.ceiling or auth.ceiling)
            if line.amount > ceiling:
                return LineResult(ceiling, ["PREAUTH_EXCEEDED"], "authorisation")
            return LineResult(line.amount, reasons, "authorisation")
        if line.code in rs.preauth_required and not line.emergency:
            return LineResult(0.0, reasons + ["PREAUTH_MISSING"], "—")

    # reference pricing — the payment rule (§3); resolve for the line's provider discipline
    rate, src, status = resolve(book, line.kind, line.code, line.discipline or tier)
    if rate is None:
        return LineResult(line.amount, reasons, src, needs_review=True)   # uncovered -> R&N review
    expected = round(rate * line.qty, 2)
    if line.amount > expected:
        reasons.append("BILLED_OVER_REFERENCE")
        if status in PAYMENT_RULE_STATUSES:
            return LineResult(expected, reasons, src)                     # reprice — pay min
        return LineResult(line.amount, reasons, src, needs_review=True)   # signal only (interdicted/endogenous)
    return LineResult(line.amount, reasons, src)      # under/at reference: pay as billed, never raised
