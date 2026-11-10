"""Claims — submit (score + persist) and read determinations."""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import desc, or_, select
from sqlalchemy.orm import Session

from pydantic import BaseModel

from .. import (
    admin_service, lifecycle_service, litigation_service, merits_service, models, offers_service,
    serious_injury_service, undertaking_service,
)
from ..db import get_db
from ..models import ClaimRecord, Determination
from ..pipeline_service import DuplicateClaim, assess_and_store
from ..pseudonymise import pseudonymise_ingest
from ..validation import SubmissionError, validate_submission
from .deps import current_user, require_role

router = APIRouter(prefix="/claims")


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
    payload = pseudonymise_ingest(payload)              # POPIA — derive P_* from a raw ID + strip PII (§2)
    try:
        payload = validate_submission(payload)          # typed + bounded (qty>0, amount>=0, bool docs, ...)
    except SubmissionError as e:
        raise HTTPException(status_code=422, detail={"errors": e.errors})
    try:
        today = date.fromisoformat(payload["today"]) if payload.get("today") else None
        return assess_and_store(db, payload, today=today)
    except DuplicateClaim as e:
        raise HTTPException(status_code=409, detail=str(e))
    except (KeyError, ValueError, TypeError) as e:
        raise HTTPException(status_code=422, detail=f"bad payload: {e}")


class RescoreIn(BaseModel):
    today: Optional[date] = None
    note: Optional[str] = None


@router.post("/{claim_id}/rescore")
def rescore(claim_id: str, body: RescoreIn = RescoreIn(), db: Session = Depends(get_db),
            user: dict = Depends(require_role("ADMIN"))) -> dict:
    """ADMIN re-determination: re-run the engine over the STORED payload (current reference data
    and signal modes) and append a new determination. The claim and its lines are never rewritten,
    so the latest determination always describes the stored record. Audit-logged."""
    rec = db.get(ClaimRecord, claim_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="claim not found")
    record = assess_and_store(db, dict(rec.raw), today=body.today, rescore=True)
    admin_service._audit(db, user, "RESCORE_CLAIM", claim_id,
                         {"note": body.note, "band": record["band"], "disposition": record["disposition"],
                          "net_payable": record["net_payable"]})
    db.commit()
    return record


@router.get("")
def list_claims(db: Session = Depends(get_db), user: dict = Depends(current_user),
                band: str | None = None, disposition: str | None = None,
                q: str | None = None,
                limit: int = Query(50, le=200), offset: int = 0) -> list[dict]:
    stmt = select(Determination).order_by(desc(Determination.id))
    if band:
        stmt = stmt.where(Determination.band == band)
    if disposition:
        stmt = stmt.where(Determination.disposition == disposition)
    if q and q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Determination.claim_id.ilike(like),
                              Determination.accident_id.ilike(like)))
    return [_det_dict(r) for r in db.scalars(stmt.limit(limit).offset(offset))]


@router.get("/{claim_id}")
def get_claim(claim_id: str, db: Session = Depends(get_db),
              user: dict = Depends(current_user)) -> dict:
    det = db.scalar(select(Determination).where(Determination.claim_id == claim_id)
                    .order_by(desc(Determination.id)))
    if det is None:
        raise HTTPException(status_code=404, detail="claim not found")
    return {"claim": _claim_dict(db.get(ClaimRecord, claim_id)), "determination": _det_dict(det)}


@router.get("/{claim_id}/workflow")
def workflow(claim_id: str, db: Session = Depends(get_db),
             user: dict = Depends(current_user)) -> dict:
    """Every operational machine for one claim + its available actions — the UI workflow panel."""
    lc = db.get(models.ClaimLifecycle, claim_id)
    m = db.get(models.MeritsDetermination, claim_id)
    sis = db.scalars(select(models.SeriousInjury)
                     .where(models.SeriousInjury.claim_id == claim_id)
                     .order_by(models.SeriousInjury.id))
    us = db.scalars(select(models.Undertaking)
                    .where(models.Undertaking.claim_id == claim_id)
                    .order_by(models.Undertaking.id))
    lits = db.scalars(select(models.Litigation)
                      .where(models.Litigation.claim_id == claim_id)
                      .order_by(models.Litigation.id))
    return {
        "claim_id": claim_id,
        "lifecycle": None if lc is None else {
            "stage": lc.stage, "actions": lifecycle_service.LIFECYCLE.actions_from(lc.stage)},
        "merits": None if m is None else {
            "status": m.status, "fault_pct": m.fault_pct, "ground": m.ground,
            "actions": merits_service.MERITS.actions_from(m.status)},
        "offer": offers_service.latest_offer(db, claim_id),
        "serious_injury": [
            {"id": s.id, "status": s.status, "list_match": s.list_match, "wpi": s.wpi,
             "narrative": s.narrative, "actions": serious_injury_service.SI.actions_from(s.status)}
            for s in sis],
        "undertakings": [
            {"id": u.id, "origin": u.origin, "status": u.status, "scope_dx": u.scope_dx,
             "actions": undertaking_service.UNDERTAKING.actions_from(u.status),
             "invoices": [
                 {"id": i.id, "status": i.status, "billed": i.billed, "payable": i.payable,
                  "reasons": i.reasons,
                  "actions": undertaking_service.INVOICE.actions_from(i.status)}
                 for i in undertaking_service.invoices_for(db, u.id)]}
            for u in us],
        "litigation": [
            {"id": lt.id, "status": lt.status, "default_judgment": lt.default_judgment,
             "actions": litigation_service.LITIGATION.actions_from(lt.status)}
            for lt in lits],
    }
