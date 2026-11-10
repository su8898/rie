"""The benchmark — one resolver, legal status on every answer (domain-logic §3).

`resolve()` returns (rate, src, legal_status). Only ENFORCEABLE/ACCEPTED drive the payment
rule (`pay min(billed, reference)`); INTERDICTED/ENDOGENOUS produce signals only. CIE guards
retained: GAZETTE_FLOOR (OCR noise), OCR_SUSPECT_RATIO (dropped-digit guard), tariff code
normalisation, NON_BENCHMARKABLE carries no overage.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from .models import normalise_code
from .vocab import D, LegalStatus, money

GAZETTE_FLOOR, OCR_SUSPECT_RATIO = 10.0, 0.33
DISP_FEE_THRESHOLD, DISP_FEE_PCT, DISP_FEE_FLAT = 155.0, 0.30, 46.50
GP_DISCIPLINE = "GP"                                   # fallback discipline for tariff resolution


@dataclass
class RefBook:
    # The payment-rule sources (negotiated, rpl, sep) hold a RATE VALUE per key: either one rate
    # (always in force) or dated versions [(effective_from, effective_to | None, rate), ...] —
    # resolved by `rate_on` for the line's service date, so a late claim prices at the rate that
    # was in force when the service was rendered, never at today's.
    negotiated: dict[tuple[str, str], object]         # (kind, code) -> rate value
    rpl: dict[str, dict[str, object]]                 # code -> {discipline -> rate value} (RAF-Δ §3)
    raf2022: dict[str, float]                         # discipline-resolved gazette rate
    empirical: dict[tuple[str, str], float]
    sep: dict[str, object]                            # NAPPI -> single exit price (rate value)
    non_benchmarkable: set[str]                       # TARIFF codes with no benchmark by design

    def __post_init__(self) -> None:                               # codes compare normalised (§3)
        self.non_benchmarkable = {normalise_code("TARIFF", x) for x in self.non_benchmarkable}


def dispensing_fee(sep: float) -> float:
    return money(D(sep) * D(DISP_FEE_PCT)) if sep < DISP_FEE_THRESHOLD else DISP_FEE_FLAT


def rate_on(value, on: Optional[date] = None) -> Optional[float]:
    """§3 — the rate in force on a service date. `value` is one rate (always in force) or dated
    versions [(effective_from, effective_to | None, rate), ...]; returns the version covering `on`
    (the latest-starting one if several do), or None when none does. With no date the latest
    version answers (the current rate)."""
    if not isinstance(value, list):
        return value
    live = [v for v in value if on is None or (v[0] <= on and (v[1] is None or on <= v[1]))]
    return max(live, key=lambda v: v[0])[2] if live else None


def resolve(book: RefBook, kind: str, code: str, discipline: str = GP_DISCIPLINE,
            on: Optional[date] = None) -> tuple[Optional[float], str, Optional[LegalStatus]]:
    """-> (rate, src, legal_status), as in force on `on` (the service date; None = current). The
    tariff rate resolves for the billing provider's discipline (exact -> GP -> cheapest). A source
    with no version in force on the date does not answer — resolution falls to the next tier.
    Only ENFORCEABLE/ACCEPTED drive the payment rule."""
    nc = normalise_code(kind, code)
    if kind == "TARIFF" and nc in book.non_benchmarkable:
        return None, "—", None
    if (kind, nc) in book.negotiated:
        neg = rate_on(book.negotiated[(kind, nc)], on)
        if neg is not None:
            return neg, "negotiated", LegalStatus.ENFORCEABLE
    if kind == "TARIFF":
        rates = {d: r for d, v in book.rpl.get(nc, {}).items() if (r := rate_on(v, on)) is not None}
        if rates:                                                # {discipline: rate in force}
            rate = rates.get(discipline) or rates.get(GP_DISCIPLINE) or min(rates.values())
            return rate, "RPL", LegalStatus.ACCEPTED
        if nc in book.raf2022 and book.raf2022[nc] >= GAZETTE_FLOOR:
            g, emp = book.raf2022[nc], book.empirical.get((kind, nc))
            if emp and g < OCR_SUSPECT_RATIO * emp:              # dropped-digit OCR guard
                return emp, "empirical", LegalStatus.ENDOGENOUS
            return g, "RAF 2022", LegalStatus.INTERDICTED
    sep = rate_on(book.sep[code], on) if kind == "NAPPI" and code in book.sep else None
    if sep is not None:
        return money(D(sep) + D(dispensing_fee(sep))), "NAPPI+fee", LegalStatus.ENFORCEABLE
    if (kind, nc) in book.empirical:
        return book.empirical[(kind, nc)], "empirical", LegalStatus.ENDOGENOUS
    return None, "—", None
