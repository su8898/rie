"""Claims — submit (score + persist) and read determinations."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import ClaimRecord, Determination
from ..pipeline_service import assess_and_store
from .deps import current_user, require_role

router = APIRouter(prefix="/claims")

_REQUIRED = ("claim_id", "claim_type", "party_token", "accident_date", "lodged_on")


def _det_dict(r: Determination) -> dict:
    return {
        "id": r.id, "claim_id": r.claim_id, "accident_id": r.accident_id,
        "accident_action": r.accident_action, "band": r.band, "score": r.score,
        "disposition": r.disposition, "validated": r.validated, "convergence": r.convergence,
        "medical_payable": r.medical_payable, "net_payable": r.net_payable,
        "eligible_to_pay": r.eligible_to_pay, "reasons": r.reasons,
        "shadow_signals": r.shadow_signals, "holds": r.holds,
        "engine_version": r.engine_version, "ruleset_effective": r.ruleset_effective,
        "reference_edition": r.reference_edition,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _claim_dict(c: ClaimRecord | None) -> dict | None:
    if c is None:
        return None
    return {
        "claim_id": c.claim_id, "claim_type": c.claim_type, "party_token": c.party_token,
        "accident_date": c.accident_date.isoformat(), "lodged_on": c.lodged_on.isoformat(),
        "raw": c.raw, "created_at": c.created_at.isoformat() if c.created_at else None,
    }


@router.post("")
def submit(payload: dict = Body(...), db: Session = Depends(get_db),
           user: dict = Depends(require_role("HANDLER", "MEDICAL_OFFICER"))) -> dict:
    missing = [k for k in _REQUIRED if k not in payload]
    if missing:
        raise HTTPException(status_code=422, detail={"missing": missing})
    try:
        today = date.fromisoformat(payload["today"]) if payload.get("today") else None
        return assess_and_store(db, payload, today=today)
    except (KeyError, ValueError, TypeError) as e:
        raise HTTPException(status_code=422, detail=f"bad payload: {e}")


@router.get("")
def list_claims(db: Session = Depends(get_db), user: dict = Depends(current_user),
                band: str | None = None, disposition: str | None = None,
                limit: int = Query(50, le=200), offset: int = 0) -> list[dict]:
    stmt = select(Determination).order_by(desc(Determination.id))
    if band:
        stmt = stmt.where(Determination.band == band)
    if disposition:
        stmt = stmt.where(Determination.disposition == disposition)
    return [_det_dict(r) for r in db.scalars(stmt.limit(limit).offset(offset))]


@router.get("/{claim_id}")
def get_claim(claim_id: str, db: Session = Depends(get_db),
              user: dict = Depends(current_user)) -> dict:
    det = db.scalar(select(Determination).where(Determination.claim_id == claim_id)
                    .order_by(desc(Determination.id)))
    if det is None:
        raise HTTPException(status_code=404, detail="claim not found")
    return {"claim": _claim_dict(db.get(ClaimRecord, claim_id)), "determination": _det_dict(det)}
