"""Line adjudication — reconcile, reprice, or refer (domain-logic §3, §5f).

Hard causation/date gates, then undertaking + pre-authorisation reconciliation, then reference
pricing (the payment rule: pay min(billed, reference) on ENFORCEABLE/ACCEPTED; signal only on
INTERDICTED/ENDOGENOUS).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from .coding import ONCE_PER_ENCOUNTER, code_rule, encounter_key, line_reference
from .models import Authorisation, Claim, Line, LineResult, Ruleset, Undertaking, normalise_code
from .reference import RefBook
from .vocab import D, PAYMENT_RULE_STATUSES, money


def find_authorisation(u: Optional[Undertaking], line: Line) -> Optional[Authorisation]:
    if not u:
        return None
    nc = normalise_code("TARIFF", line.code)
    for auth in u.authorisations:
        if auth.status == "APPROVED" and nc in auth.codes \
           and auth.valid_from <= line.service_date <= auth.valid_to:
            return auth
    return None


def line_key(party_token: str, line: Line) -> tuple:
    """The identity of a billed service for pay-once checks (§4e/§4f): who, by whom, when, what
    (normalised code), how much."""
    return (party_token, line.provider_id, line.service_date, line.kind,
            normalise_code(line.kind, line.code), line.amount)


def consume_authorisation(auth: Authorisation, line: Line, usage: dict) -> float:
    """§5f — the promise is finite: units up to qty_limit and rand up to the ceiling, consumed
    across every line the authorisation covers. Returns the payable rand for this line."""
    used_qty, used_rand = usage.get(id(auth), (Decimal(0), Decimal(0)))
    qty = D(line.qty) if line.qty > 0 else Decimal(1)
    units = min(qty, D(auth.qty_limit) - used_qty) if auth.qty_limit > 0 else qty
    rand_room = D(auth.ceiling) - used_rand
    payable = money(max(min(D(line.amount) / qty * max(units, Decimal(0)), rand_room), Decimal(0)))
    usage[id(auth)] = (used_qty + qty, used_rand + D(payable))
    return payable


def adjudicate_line(c: Claim, line: Line, book: RefBook, rs: Ruleset,
                    tier: str, seen: set, accident_dx_regions: set[str],
                    prior: frozenset = frozenset(), auth_usage: Optional[dict] = None) -> LineResult:
    """`seen` is this claim's lines so far; `prior` is every line already paid on another
    claim for this party (threaded by the caller — the s17(5) control); `auth_usage` tracks
    authorisation consumption across the claim's lines."""
    reasons: list[str] = []
    nc = normalise_code(line.kind, line.code)

    # hard causation/date gates (§4d)
    if line.service_date < c.accident_date:
        return LineResult(0.0, ["SERVICE_BEFORE_ACCIDENT"], "—")
    key = line_key(c.party_token, line)
    if key in prior:                                  # §4e — s17(5): already paid on another claim
        return LineResult(0.0, ["SUPPLIER_PRECLUSION"], "—")
    if key in seen:                                   # §4f — pay the first occurrence only
        return LineResult(0.0, ["DUPLICATE_LINE"], "—")
    seen.add(key)
    if code_rule(book, line)[0] == ONCE_PER_ENCOUNTER:           # §3b — the tariff's own limit
        once = encounter_key(c.party_token, line)
        if once in prior or once in seen:             # billed again at any amount, on any claim
            return LineResult(0.0, ["UNBUNDLING_CONFLICT"], "—")
        seen.add(once)
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
            payable = consume_authorisation(auth, line, auth_usage if auth_usage is not None else {})
            if payable < line.amount:
                return LineResult(payable, ["PREAUTH_EXCEEDED"], "authorisation")
            return LineResult(line.amount, reasons, "authorisation")
        if nc in rs.preauth_required and not line.emergency:
            return LineResult(0.0, reasons + ["PREAUTH_MISSING"], "—")

    # reference pricing — the payment rule (§3, §3b); resolved for the line's provider
    # discipline and service date, and priced by the code's own rule where it has one
    expected, src, status = line_reference(c, line, book, tier)
    if expected is None:                              # uncovered -> hard R&N review, never paid as billed
        return LineResult(line.amount, reasons + ["REFERENCE_UNRESOLVED"], src, needs_review=True)
    if line.amount > expected:
        reasons.append("BILLED_OVER_REFERENCE")
        if status in PAYMENT_RULE_STATUSES:
            return LineResult(expected, reasons, src)                     # reprice — pay min
        return LineResult(line.amount, reasons, src, needs_review=True)   # signal only (interdicted/endogenous)
    return LineResult(line.amount, reasons, src)      # under/at reference: pay as billed, never raised
