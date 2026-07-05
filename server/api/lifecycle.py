"""Claim lifecycle — read state + available actions, drive transitions."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import lifecycle_service, models
from ..db import get_db
from .deps import current_user

router = APIRouter(prefix="/lifecycle")


def _log(x) -> dict:
    return {"from": x.from_state, "to": x.to_state, "action": x.action, "actor": x.actor,
            "role": x.role, "at": x.at.isoformat() if x.at else None, "detail": x.detail}


@router.get("/{claim_id}")
def get_lifecycle(claim_id: str, db: Session = Depends(get_db),
                  user: dict = Depends(current_user)) -> dict:
    lc = db.get(models.ClaimLifecycle, claim_id)
    if lc is None:
        raise HTTPException(status_code=404, detail="no lifecycle for claim")
    return {"claim_id": claim_id, "stage": lc.stage,
            "actions": lifecycle_service.LIFECYCLE.actions_from(lc.stage),
            "history": [_log(x) for x in lifecycle_service.history(db, claim_id)]}


@router.post("/{claim_id}/{action}")
def transition(claim_id: str, action: str, db: Session = Depends(get_db),
               user: dict = Depends(current_user)) -> dict:
    lc = lifecycle_service.transition(db, claim_id, action, user)
    return {"claim_id": claim_id, "stage": lc.stage,
            "actions": lifecycle_service.LIFECYCLE.actions_from(lc.stage)}
