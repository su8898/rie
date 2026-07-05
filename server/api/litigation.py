"""Litigation router — open a matter, read state + available actions, drive transitions.

plead / set_trial / settle / judgment / default_judgment are legal's; order_paid is admin's;
close is either. Role enforcement on transitions happens inside sm.fire.
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import litigation_service, models
from ..db import get_db
from .deps import current_user, require_role

router = APIRouter(prefix="/litigation")


def _log(x) -> dict:
    return {"from": x.from_state, "to": x.to_state, "action": x.action, "actor": x.actor,
            "role": x.role, "at": x.at.isoformat() if x.at else None, "detail": x.detail}


def _dict(lit) -> dict:
    return {"id": lit.id, "claim_id": lit.claim_id, "status": lit.status,
            "default_judgment": lit.default_judgment}


@router.post("")
def create(body: dict = Body(default={}), db: Session = Depends(get_db),
           user: dict = Depends(require_role("LEGAL"))) -> dict:
    lit = litigation_service.create(db, body["claim_id"], user)
    return _dict(lit)


@router.get("/{lit_id}")
def get_litigation(lit_id: int, db: Session = Depends(get_db),
                   user: dict = Depends(current_user)) -> dict:
    lit = db.get(models.Litigation, lit_id)
    if lit is None:
        raise HTTPException(status_code=404, detail="no litigation record")
    return {**_dict(lit), "actions": litigation_service.LITIGATION.actions_from(lit.status),
            "history": [_log(x) for x in litigation_service.history(db, lit_id)]}


@router.post("/{lit_id}/{action}")
def transition(lit_id: int, action: str, db: Session = Depends(get_db),
               user: dict = Depends(current_user)) -> dict:
    lit = litigation_service.transition(db, lit_id, action, user)
    return _dict(lit)
