"""Serious-injury (RAF 4) router — submit an assessment, read state + actions, drive transitions.

accept / reject are the medical officer's; a rejection is appealed to the HPCSA (legal) and then
upheld or dismissed. Role enforcement on transitions happens inside sm.fire.
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, serious_injury_service
from ..db import get_db
from .deps import current_user, require_role

router = APIRouter(prefix="/serious-injury")


def _log(x) -> dict:
    return {"from": x.from_state, "to": x.to_state, "action": x.action, "actor": x.actor,
            "role": x.role, "at": x.at.isoformat() if x.at else None, "detail": x.detail}


def _dict(si) -> dict:
    return {"id": si.id, "claim_id": si.claim_id, "status": si.status,
            "list_match": si.list_match, "wpi": si.wpi, "narrative": si.narrative}


@router.post("")
def create(body: dict = Body(default={}), db: Session = Depends(get_db),
           user: dict = Depends(require_role("MEDICAL_OFFICER"))) -> dict:
    si = serious_injury_service.create(
        db, body["claim_id"], list_match=body.get("list_match", False),
        wpi=body.get("wpi"), narrative=body.get("narrative", False))
    return _dict(si)


@router.get("/{si_id}")
def get_si(si_id: int, db: Session = Depends(get_db),
           user: dict = Depends(current_user)) -> dict:
    si = db.get(models.SeriousInjury, si_id)
    if si is None:
        raise HTTPException(status_code=404, detail="no serious-injury record")
    return {**_dict(si), "actions": serious_injury_service.SI.actions_from(si.status),
            "history": [_log(x) for x in serious_injury_service.history(db, si_id)]}


@router.post("/{si_id}/{action}")
def transition(si_id: int, action: str, db: Session = Depends(get_db),
               user: dict = Depends(current_user)) -> dict:
    si = serious_injury_service.transition(db, si_id, action, user)
    return _dict(si)
