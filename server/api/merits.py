"""Merits determination — accept (fault %) / reject (s19 ground) / appeal."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import merits_service, models
from ..db import get_db
from .deps import current_user

router = APIRouter(prefix="/merits")


def _log(x) -> dict:
    return {"from": x.from_state, "to": x.to_state, "action": x.action, "actor": x.actor,
            "role": x.role, "at": x.at.isoformat() if x.at else None, "detail": x.detail}


def _dict(m) -> dict:
    return {"claim_id": m.claim_id, "status": m.status, "fault_pct": m.fault_pct, "ground": m.ground}


@router.get("/{claim_id}")
def get_merits(claim_id: str, db: Session = Depends(get_db),
               user: dict = Depends(current_user)) -> dict:
    m = db.get(models.MeritsDetermination, claim_id)
    if m is None:
        raise HTTPException(status_code=404, detail="no merits determination for claim")
    return {**_dict(m), "actions": merits_service.MERITS.actions_from(m.status),
            "history": [_log(x) for x in merits_service.history(db, claim_id)]}


@router.post("/{claim_id}/{action}")
def decide(claim_id: str, action: str, body: dict = Body(default={}),
           db: Session = Depends(get_db), user: dict = Depends(current_user)) -> dict:
    m = merits_service.decide(db, claim_id, action, user,
                              fault_pct=body.get("fault_pct"), ground=body.get("ground"))
    return _dict(m)
