"""Objection / dispute register — internal reconsideration, HPCSA tribunal, litigation hand-off.

Static route (/analytics) is declared before /{dispute_id} so it is not shadowed.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from .. import disputes_service as svc, models, work_query
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


@router.get("/search")
def search(q: str = Query("", max_length=100), subject: str = "", status: str = "", raised_by: str = "",
           channel: str = "", open_only: bool = False, overdue: bool = False,
           claim_id: str = Query("", max_length=64), sort: Literal["opened", "deadline"] = "opened",
           direction: Literal["asc", "desc"] = "desc", limit: int = Query(25, ge=1, le=200),
           offset: int = Query(0, ge=0), db: Session = Depends(get_db),
           user: dict = Depends(current_user)) -> dict:
    """The dispute worklist: `{rows, total, counts}`."""
    return work_query.search_disputes(db, q=q, subject=subject, status=status, raised_by=raised_by,
                                      channel=channel, open_only=open_only, overdue=overdue,
                                      claim_id=claim_id, sort=sort, direction=direction,
                                      limit=limit, offset=offset)


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


@router.patch("/{dispute_id}")
def update_dispute(dispute_id: int, body: dict = Body(...), db: Session = Depends(get_db),
                   user: dict = Depends(current_user)) -> dict:
    """Correct the grounds of a dispute that is still open (logged)."""
    return svc.item_dict(work_query.update_dispute(db, dispute_id, user, grounds=body.get("grounds")))


@router.get("/{dispute_id}/history")
def dispute_history(dispute_id: int, db: Session = Depends(get_db),
                    user: dict = Depends(current_user)) -> list[dict]:
    return work_query.history(db, "dispute", dispute_id)


@router.post("/{dispute_id}/{action}")
def transition(dispute_id: int, action: str, body: dict = Body(default={}),
               db: Session = Depends(get_db), user: dict = Depends(current_user)) -> dict:
    d = svc.transition(db, dispute_id, action, user, outcome=body.get("outcome"),
                       channel=body.get("channel"), linked_ref=body.get("linked_ref"))
    return svc.item_dict(d)
