"""Audit / clawback recovery — the post-payment recovery queue + ROI."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from .. import audit_service as svc, models
from ..db import get_db
from .deps import current_user, require_role

router = APIRouter(prefix="/audit")


@router.get("")
def list_items(db: Session = Depends(get_db), user: dict = Depends(current_user),
               status: str | None = None) -> list[dict]:
    stmt = select(models.AuditQueue).order_by(desc(models.AuditQueue.id))
    if status:
        stmt = stmt.where(models.AuditQueue.status == status)
    return [svc.item_dict(a) for a in db.scalars(stmt)]


@router.post("/sweep")
def sweep(threshold: float = Query(20.0, ge=0, le=100), db: Session = Depends(get_db),
          user: dict = Depends(require_role("INVESTIGATOR"))) -> dict:
    opened = svc.recovery_sweep(db, user, threshold=threshold)
    return {"opened": opened, "n": len(opened), "threshold": threshold}


@router.get("/roi")
def roi(db: Session = Depends(get_db), user: dict = Depends(current_user)) -> dict:
    return svc.roi(db)


@router.get("/{audit_id}")
def get_item(audit_id: int, db: Session = Depends(get_db),
             user: dict = Depends(current_user)) -> dict:
    a = db.get(models.AuditQueue, audit_id)
    if a is None:
        raise HTTPException(status_code=404, detail="audit item not found")
    return svc.item_dict(a)


@router.post("/{audit_id}/{action}")
def transition(audit_id: int, action: str, body: dict = Body(default={}),
               db: Session = Depends(get_db), user: dict = Depends(current_user)) -> dict:
    a = svc.transition(db, audit_id, action, user,
                       amount=body.get("amount"), outcome=body.get("outcome"))
    return svc.item_dict(a)
