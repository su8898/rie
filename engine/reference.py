"""The benchmark — one resolver, legal status on every answer (domain-logic §3).

`resolve()` returns (rate, src, legal_status). Only ENFORCEABLE/ACCEPTED drive the payment
rule (`pay min(billed, reference)`); INTERDICTED/ENDOGENOUS produce signals only. CIE guards
retained: GAZETTE_FLOOR (OCR noise), OCR_SUSPECT_RATIO (dropped-digit guard), tariff code
normalisation, NON_BENCHMARKABLE carries no overage.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .models import normalise_code
from .vocab import D, LegalStatus, money

GAZETTE_FLOOR, OCR_SUSPECT_RATIO = 10.0, 0.33
DISP_FEE_THRESHOLD, DISP_FEE_PCT, DISP_FEE_FLAT = 155.0, 0.30, 46.50
GP_DISCIPLINE = "GP"                                   # fallback discipline for tariff resolution


@dataclass
class RefBook:
    negotiated: dict[tuple[str, str], float]          # (kind, code) -> rate
    rpl: dict[str, dict[str, float]]                  # code -> {discipline -> rate} (RAF-Δ §3)
    raf2022: dict[str, float]                         # discipline-resolved gazette rate
    empirical: dict[tuple[str, str], float]
    sep: dict[str, float]                             # NAPPI -> single exit price
    non_benchmarkable: set[str]                       # TARIFF codes with no benchmark by design

    def __post_init__(self) -> None:                               # codes compare normalised (§3)
        self.non_benchmarkable = {normalise_code("TARIFF", x) for x in self.non_benchmarkable}


def dispensing_fee(sep: float) -> float:
    return money(D(sep) * D(DISP_FEE_PCT)) if sep < DISP_FEE_THRESHOLD else DISP_FEE_FLAT


def resolve(book: RefBook, kind: str, code: str, discipline: str = GP_DISCIPLINE
            ) -> tuple[Optional[float], str, Optional[LegalStatus]]:
    """-> (rate, src, legal_status). The tariff rate resolves for the billing provider's
    discipline (exact -> GP -> cheapest). Only ENFORCEABLE/ACCEPTED drive the payment rule."""
    nc = normalise_code(kind, code)
    if kind == "TARIFF" and nc in book.non_benchmarkable:
        return None, "—", None
    if (kind, nc) in book.negotiated:
        return book.negotiated[(kind, nc)], "negotiated", LegalStatus.ENFORCEABLE
    if kind == "TARIFF":
        if nc in book.rpl:
            rates = book.rpl[nc]                                 # {discipline: rate}
            rate = rates.get(discipline) or rates.get(GP_DISCIPLINE) or min(rates.values())
            return rate, "RPL", LegalStatus.ACCEPTED
        if nc in book.raf2022 and book.raf2022[nc] >= GAZETTE_FLOOR:
            g, emp = book.raf2022[nc], book.empirical.get((kind, nc))
            if emp and g < OCR_SUSPECT_RATIO * emp:              # dropped-digit OCR guard
                return emp, "empirical", LegalStatus.ENDOGENOUS
            return g, "RAF 2022", LegalStatus.INTERDICTED
    if kind == "NAPPI" and code in book.sep:
        sep = book.sep[code]
        return money(D(sep) + D(dispensing_fee(sep))), "NAPPI+fee", LegalStatus.ENFORCEABLE
    if (kind, nc) in book.empirical:
        return book.empirical[(kind, nc)], "empirical", LegalStatus.ENDOGENOUS
    return None, "—", None
