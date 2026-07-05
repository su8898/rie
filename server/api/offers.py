"""Offer builder — compute heads of damage into an offer (read-only what-if)."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..offers_service import compute_offer
from .deps import require_role

router = APIRouter(prefix="/offer")

_REQUIRED = ("claim_id", "claim_type", "party_token", "accident_date", "lodged_on")


@router.post("")
def offer(payload: dict = Body(...), db: Session = Depends(get_db),
          user: dict = Depends(require_role("HANDLER"))) -> dict:
    missing = [k for k in _REQUIRED if k not in payload]
    if missing:
        raise HTTPException(status_code=422, detail={"missing": missing})
    try:
        today = date.fromisoformat(payload["today"]) if payload.get("today") else None
        return compute_offer(db, payload, today=today)
    except (KeyError, ValueError, TypeError) as e:
        raise HTTPException(status_code=422, detail=f"bad payload: {e}")
