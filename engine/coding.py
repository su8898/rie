"""Coding rules — what the tariff itself says about a code (domain-logic §3b).

A code rule is reference data: TARIFF code -> (rule, param). The rules are the tariff's own
billing rules, so they are payment rules, never statistics: a once-per-encounter code is paid
once, and a time modifier is priced by its ladder, not by a flat rate per minute.
"""
from __future__ import annotations

from decimal import ROUND_CEILING, Decimal
from typing import Optional

from .models import Claim, Line, normalise_code
from .reference import RefBook, resolve
from .vocab import D, LegalStatus, money

ONCE_PER_ENCOUNTER = "ONCE_PER_ENCOUNTER"     # the description limits the code to once per encounter
TIME_BLOCK = "TIME_BLOCK"                     # qty is MINUTES: one block per `param` minutes or part
TIME_ANAES = "TIME_ANAES"                     # qty is MINUTES: a block per 15 min or part in the first hour, 1.5 after
TIME_FIRST_HOUR = "TIME_FIRST_HOUR"           # qty is MINUTES: a block for the first hour, then a third per 15 min or part
PCT_OF_TIME = "PCT_OF_TIME"                   # `param` share of the anaesthetic time billed with it
TIME_RULES = {TIME_BLOCK, TIME_ANAES, TIME_FIRST_HOUR}
ANAES_TIME_RULES = {TIME_ANAES, TIME_FIRST_HOUR}       # what a PCT_OF_TIME modifier is a percentage of
CODE_RULES = TIME_RULES | {ONCE_PER_ENCOUNTER, PCT_OF_TIME}


def code_rule(book: RefBook, line: Line) -> tuple[Optional[str], float]:
    """The coding rule on a line's code — (None, 0.0) for an ordinary code or any NAPPI line."""
    if line.kind != "TARIFF":
        return None, 0.0
    return book.code_rules.get(normalise_code("TARIFF", line.code), (None, 0.0))


def encounter_key(party_token: str, line: Line) -> tuple:
    """One encounter's use of a once-only code: who, by whom, when, what — at any amount."""
    return ("ONCE", party_token, line.provider_id, line.service_date,
            normalise_code("TARIFF", line.code))


def blocks(minutes: Decimal, size) -> Decimal:
    """Billing blocks "or part thereof": minutes / size, rounded up."""
    return (minutes / D(size)).to_integral_value(rounding=ROUND_CEILING)


def time_total(rule: str, param: float, rate: float, minutes: float) -> Decimal:
    """The reference TOTAL for a time modifier billed in minutes; `rate` is its block rate."""
    m, r = D(minutes), D(rate)
    if rule == TIME_BLOCK:
        return r * blocks(m, param or 30)
    later = blocks(max(m - 60, Decimal(0)), 15)       # 15-minute periods beyond the first hour
    if rule == TIME_ANAES:
        return r * blocks(min(m, Decimal(60)), 15) + r * Decimal("1.5") * later
    return r + r / 3 * later                          # TIME_FIRST_HOUR


def line_reference(c: Claim, line: Line, book: RefBook, tier: str
                   ) -> tuple[Optional[float], str, Optional[LegalStatus]]:
    """-> (the reference TOTAL for the line | None, src, legal_status). An ordinary code is
    rate x qty. A time modifier is billed in minutes and priced by its ladder off the block rate.
    A percentage-of-time modifier is a share of the anaesthetic-time lines billed with it (same
    provider, same day); with none on the claim it is a percentage of nothing and does not
    resolve — the line goes to review."""
    rule, param = code_rule(book, line)
    if rule == PCT_OF_TIME:
        base, src, status = Decimal(0), "—", None
        for sib in c.lines:
            if (sib.provider_id, sib.service_date) == (line.provider_id, line.service_date) \
               and code_rule(book, sib)[0] in ANAES_TIME_RULES:
                total, sib_src, sib_status = line_reference(c, sib, book, tier)
                if total is not None:
                    base, src, status = base + D(total), sib_src, sib_status
        return (money(D(param) * base), src, status) if base > 0 else (None, "—", None)
    rate, src, status = resolve(book, line.kind, line.code, line.discipline or tier,
                                line.service_date)
    if rate is None:
        return None, src, status
    if rule in TIME_RULES:
        return money(time_total(rule, param, rate, line.qty)), src, status
    return money(D(rate) * D(line.qty)), src, status
