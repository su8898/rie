"""Objection / dispute register — internal reconsideration, HPCSA tribunal, litigation hand-off.

Static route (/analytics) is declared before /{dispute_id} so it is not shadowed.
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from .. import disputes_service as svc, models
from ..db import get_db
from .deps import current_user

router = APIRouter(prefix="/disputes")


@router.get("")
def list_disputes(db: Session = Depends(get_db), user: dict = Depends(current_user),
                  subject: str | None = None, status: str | None = None,
                  claim_id: str | None = None) -> list[dict]:
    stmt = select(models.Dispute).order_by(desc(models.Dispute.id))
    if subject:
        stmt = stmt.where(models.Dispute.subject == subject)
    if status:
        stmt = stmt.where(models.Dispute.status == status)
    if claim_id:
        stmt = stmt.where(models.Dispute.claim_id == claim_id)
    return [svc.item_dict(d) for d in db.scalars(stmt)]


@router.post("")
def lodge(body: dict = Body(...), db: Session = Depends(get_db),
          user: dict = Depends(current_user)) -> dict:
    d = svc.lodge(db, user, claim_id=body.get("claim_id", ""), subject=body.get("subject", ""),
                  raised_by=body.get("raised_by", ""), grounds=body.get("grounds", ""))
    return svc.item_dict(d)


@router.get("/analytics")
def analytics(db: Session = Depends(get_db), user: dict = Depends(current_user)) -> dict:
    return svc.analytics(db)


@router.get("/{dispute_id}")
def get_dispute(dispute_id: int, db: Session = Depends(get_db),
                user: dict = Depends(current_user)) -> dict:
    d = db.get(models.Dispute, dispute_id)
    if d is None:
        raise HTTPException(status_code=404, detail="dispute not found")
    return svc.item_dict(d)


@router.post("/{dispute_id}/{action}")
def transition(dispute_id: int, action: str, body: dict = Body(default={}),
               db: Session = Depends(get_db), user: dict = Depends(current_user)) -> dict:
    d = svc.transition(db, dispute_id, action, user, outcome=body.get("outcome"),
                       channel=body.get("channel"), linked_ref=body.get("linked_ref"))
    return svc.item_dict(d)
