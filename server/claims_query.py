"""Claims as an operator reads them — the worklist and the full claim record.

The worklist is one row per claim (its LATEST determination) joined to the claim itself and to
its billing lines, so a row can show who billed, what was billed and what is payable, and can be
filtered and sorted on those. The record adds what a handler needs to decide a claim: each
adjudicated line with what was paid and why, the determination history, the payment trail and
what the practice register knows about each practice on it.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import asc, desc, func, or_, select
from sqlalchemy.orm import Session

import engine

from . import provider_registry_service, provider_service
from .models import (BillingLineRecord, ClaimRecord, Determination, PaymentBatch, PaymentInstruction,
                     latest_determination_ids)

SORTS = {
    "received": Determination.id,                    # submission order
    "claim": Determination.claim_id,
    "lodged": ClaimRecord.lodged_on,
    "payable": Determination.net_payable,
    "score": Determination.score,
}


def _billed(db: Session, claim_ids: list[str]) -> dict[str, dict]:
    """Billed total and the practices billing, per claim."""
    out: dict[str, dict] = {c: {"billed": 0.0, "providers": []} for c in claim_ids}
    if not claim_ids:
        return out
    for cid, provider, billed in db.execute(
            select(BillingLineRecord.claim_id, BillingLineRecord.provider_id,
                   func.sum(BillingLineRecord.billed))
            .where(BillingLineRecord.claim_id.in_(claim_ids))
            .group_by(BillingLineRecord.claim_id, BillingLineRecord.provider_id)):
        out[cid]["billed"] = engine.money(engine.D(out[cid]["billed"]) + engine.D(billed or 0))
        if provider:
            out[cid]["providers"].append(provider)
    return out


def list_claims(db: Session, *, band: Optional[str] = None, disposition: Optional[str] = None,
                q: Optional[str] = None, needs_review: Optional[bool] = None,
                claim_type: Optional[str] = None, eligible: Optional[bool] = None,
                provider_id: Optional[str] = None, lodged_from: Optional[date] = None,
                lodged_to: Optional[date] = None, sort: str = "received", direction: str = "desc",
                limit: int = 50, offset: int = 0) -> tuple[list[tuple], int]:
    """→ ([(determination, claim | None, {billed, providers})], total matching)."""
    stmt = (select(Determination, ClaimRecord)
            .outerjoin(ClaimRecord, ClaimRecord.claim_id == Determination.claim_id)
            .where(Determination.id.in_(latest_determination_ids())))
    if band:
        stmt = stmt.where(Determination.band == band)
    if disposition:
        stmt = stmt.where(Determination.disposition == disposition)
    if needs_review is not None:
        stmt = stmt.where(Determination.needs_review.is_(needs_review))
    if eligible is not None:
        stmt = stmt.where(Determination.eligible_to_pay.is_(eligible))
    if claim_type:
        stmt = stmt.where(ClaimRecord.claim_type == claim_type)
    if lodged_from:
        stmt = stmt.where(ClaimRecord.lodged_on >= lodged_from)
    if lodged_to:
        stmt = stmt.where(ClaimRecord.lodged_on <= lodged_to)
    if provider_id and provider_id.strip():
        stmt = stmt.where(Determination.claim_id.in_(
            select(BillingLineRecord.claim_id)
            .where(BillingLineRecord.provider_id.ilike(f"%{provider_id.strip()}%"))))
    if q and q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Determination.claim_id.ilike(like), Determination.accident_id.ilike(like),
                              ClaimRecord.party_token.ilike(like)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    column = SORTS.get(sort, Determination.id)
    order = asc if direction == "asc" else desc
    rows = db.execute(stmt.order_by(order(column), desc(Determination.id))
                      .limit(limit).offset(offset)).all()
    billed = _billed(db, [det.claim_id for det, _claim in rows])
    return [(det, claim, billed[det.claim_id]) for det, claim in rows], total


def _batch_id(db: Session, claim_id: str):
    """The payment run holding the claim's latest live instruction (operators only)."""
    return db.scalar(
        select(PaymentInstruction.batch_id)
        .join(PaymentBatch, PaymentBatch.id == PaymentInstruction.batch_id)
        .where(PaymentInstruction.claim_id == claim_id, PaymentBatch.status != "CANCELLED")
        .order_by(PaymentInstruction.id.desc()))


def claim_extras(db: Session, claim_id: str) -> dict:
    """What the claim record page shows beyond the claim and its latest determination."""
    lines = [{
        "id": l.id, "provider_id": l.provider_id, "kind": l.kind, "code": l.code,
        "service_date": l.service_date.isoformat() if l.service_date else None,
        "billed": l.billed, "reference": l.reference, "payable": l.payable,
        "reduced": engine.money(max(engine.D(l.billed) - engine.D(l.payable), engine.D(0))),
        "source": l.src, "legal_status": l.legal_status, "needs_review": bool(l.needs_review),
        "reasons": list(l.reasons or []),
    } for l in db.scalars(select(BillingLineRecord).where(BillingLineRecord.claim_id == claim_id)
                          .order_by(BillingLineRecord.id))]
    history = [{
        "id": d.id, "created_at": d.created_at.isoformat() if d.created_at else None,
        "band": d.band, "score": d.score, "disposition": d.disposition,
        "net_payable": d.net_payable, "eligible_to_pay": d.eligible_to_pay,
        "reasons": list(d.reasons or []), "engine_version": d.engine_version,
    } for d in db.scalars(select(Determination).where(Determination.claim_id == claim_id)
                          .order_by(desc(Determination.id)))]
    providers = sorted({l["provider_id"] for l in lines if l["provider_id"]})
    return {
        "lines": lines, "history": history, "payment": {**provider_service._payment(db, claim_id), "batch_id": _batch_id(db, claim_id)},
        "billed": engine.money(sum((engine.D(l["billed"]) for l in lines), engine.D(0))),
        "practices": [provider_registry_service.resolve_identity(db, p) for p in providers],
    }
