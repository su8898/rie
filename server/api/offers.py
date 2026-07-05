"""Offer builder — compute heads of damage into an offer (read-only what-if)."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..offers_service import compute_offer, latest_offer, persist_offer
from .deps import current_user, require_role

router = APIRouter(prefix="/offer")

_REQUIRED = ("claim_id", "claim_type", "party_token", "accident_date", "lodged_on")


@router.post("")
def preview(payload: dict = Body(...), db: Session = Depends(get_db),
            user: dict = Depends(require_role("HANDLER"))) -> dict:
    """Stateless what-if offer from a full claim payload (not persisted)."""
    missing = [k for k in _REQUIRED if k not in payload]
    if missing:
        raise HTTPException(status_code=422, detail={"missing": missing})
    try:
        today = date.fromisoformat(payload["today"]) if payload.get("today") else None
        return compute_offer(db, payload, today=today)
    except (KeyError, ValueError, TypeError) as e:
        raise HTTPException(status_code=422, detail=f"bad payload: {e}")


@router.post("/{claim_id}")
def build(claim_id: str, body: dict = Body(default={}), db: Session = Depends(get_db),
          user: dict = Depends(require_role("HANDLER"))) -> dict:
    """Assemble + persist an offer for a stored claim (ASSEMBLED, or HELD if merits pending)."""
    try:
        return persist_offer(db, claim_id, body.get("heads_input", {}), user)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{claim_id}")
def get_offer(claim_id: str, db: Session = Depends(get_db),
              user: dict = Depends(current_user)) -> dict:
    o = latest_offer(db, claim_id)
    if o is None:
        raise HTTPException(status_code=404, detail="no offer for claim")
    return o
