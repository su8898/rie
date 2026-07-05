"""Investigation / review cases — lanes, SLA, outcome capture (domain-logic §8e).

Static routes (/analytics, /labels) are declared before /{case_id} so they are not shadowed.
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from .. import cases_service as svc, models
from ..db import get_db
from .deps import current_user

router = APIRouter(prefix="/cases")


@router.get("")
def list_cases(db: Session = Depends(get_db), user: dict = Depends(current_user),
               lane: str | None = None, status: str | None = None,
               mine: bool = False) -> list[dict]:
    stmt = select(models.Case).order_by(desc(models.Case.id))
    if lane:
        stmt = stmt.where(models.Case.lane == lane)
    if status:
        stmt = stmt.where(models.Case.status == status)
    if mine:
        stmt = stmt.where(models.Case.assigned_to == user.get("username"))
    return [svc.item_dict(c) for c in db.scalars(stmt)]


@router.post("")
def open_case(body: dict = Body(...), db: Session = Depends(get_db),
              user: dict = Depends(current_user)) -> dict:
    c = svc.open_case(db, user, lane=body.get("lane", ""), reason=body.get("reason", ""),
                      claim_id=body.get("claim_id"), priority=int(body.get("priority", 3)),
                      rand_at_stake=body.get("rand_at_stake", 0.0))
    return svc.item_dict(c)


@router.get("/analytics")
def analytics(db: Session = Depends(get_db), user: dict = Depends(current_user)) -> dict:
    return svc.analytics(db)


@router.get("/labels")
def labels(db: Session = Depends(get_db), user: dict = Depends(current_user)) -> list[dict]:
    return svc.labels(db)


@router.get("/{case_id}")
def get_case(case_id: int, db: Session = Depends(get_db),
             user: dict = Depends(current_user)) -> dict:
    c = db.get(models.Case, case_id)
    if c is None:
        raise HTTPException(status_code=404, detail="case not found")
    return svc.item_dict(c)


@router.get("/{case_id}/notes")
def list_notes(case_id: int, db: Session = Depends(get_db),
               user: dict = Depends(current_user)) -> list[dict]:
    return svc.notes(db, case_id)


@router.post("/{case_id}/notes")
def add_note(case_id: int, body: dict = Body(...), db: Session = Depends(get_db),
             user: dict = Depends(current_user)) -> dict:
    n = svc.add_note(db, case_id, user, body.get("body", ""))
    return {"id": n.id, "case_id": case_id}


@router.post("/{case_id}/{action}")
def transition(case_id: int, action: str, body: dict = Body(default={}),
               db: Session = Depends(get_db), user: dict = Depends(current_user)) -> dict:
    c = svc.transition(db, case_id, action, user, verdict=body.get("verdict"),
                       root_cause=body.get("root_cause"), recovered=body.get("recovered"),
                       prevented=body.get("prevented"))
    return svc.item_dict(c)
