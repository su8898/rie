"""Leakage accounting — payment-integrity decomposition (domain-logic §11).

Splits billed rand into: within-reference (payable), repricing saving (billed above an
ENFORCEABLE/ACCEPTED reference — prevented at adjudication), over-reference *signal* (billed
above an INTERDICTED/ENDOGENOUS reference — a negotiation target, not captured), dedupe
exposure (duplicate lines), and uncovered (no reference).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models


def _bucket(lines) -> dict:
    within = repricing = over_signal = dedupe = uncovered = billed_total = 0.0
    for r in lines:
        billed_total += r.billed
        if "DUPLICATE_LINE" in (r.reasons or []):
            dedupe += r.billed
            continue
        if r.reference is None:
            uncovered += r.billed
            continue
        within += r.payable
        if r.billed > r.payable:                               # repriced to an enforceable/accepted ref
            repricing += r.billed - r.payable
        elif r.legal_status in ("INTERDICTED", "ENDOGENOUS") and r.billed > r.reference:
            over_signal += r.billed - r.reference              # signal only — not captured
    return {
        "billed_total": round(billed_total, 2),
        "within_reference": round(within, 2),
        "repricing_saving": round(repricing, 2),
        "over_reference_signal": round(over_signal, 2),
        "dedupe_exposure": round(dedupe, 2),
        "uncovered": round(uncovered, 2),
    }


def portfolio_leakage(db: Session) -> dict:
    lines = list(db.scalars(select(models.BillingLineRecord)))
    return {**_bucket(lines), "lines": len(lines)}


def claim_leakage(db: Session, claim_id: str) -> dict:
    lines = list(db.scalars(
        select(models.BillingLineRecord).where(models.BillingLineRecord.claim_id == claim_id)))
    return {"claim_id": claim_id, **_bucket(lines), "lines": len(lines)}
