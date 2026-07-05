"""The accident graph — the episode view with live convergence per accident."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

import engine

from ..adapter import accident_to_engine
from ..db import get_db
from ..models import AccidentRecord
from .deps import current_user

router = APIRouter(prefix="/accidents")


def _acc_dict(r: AccidentRecord) -> dict:
    return {
        "accident_id": r.accident_id, "case_number": r.case_number,
        "when": r.when_.isoformat(), "where": r.where_, "parties": r.parties,
        "vehicles": r.vehicles, "oar_occupants": r.oar_occupants,
        "claims": r.claims, "n_claims": len(r.claims or []),
        "convergence": engine.convergence(accident_to_engine(r)),
    }


@router.get("")
def list_accidents(db: Session = Depends(get_db), user: dict = Depends(current_user)) -> list[dict]:
    return [_acc_dict(r) for r in db.scalars(select(AccidentRecord))]


@router.get("/{accident_id}")
def get_accident(accident_id: str, db: Session = Depends(get_db),
                 user: dict = Depends(current_user)) -> dict:
    r = db.get(AccidentRecord, accident_id)
    if r is None:
        raise HTTPException(status_code=404, detail="accident not found")
    return _acc_dict(r)
