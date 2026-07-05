"""Provider->fund submission rails endpoints (JWS-authenticated, not the operator session)."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import rails_service
from ..config import RAILS_SECRET
from ..db import get_db

router = APIRouter(prefix="/rails/v1")


@router.post("/claims")
def submit(request: Request, payload: dict = Body(...), db: Session = Depends(get_db)) -> dict:
    today = date.fromisoformat(payload["today"]) if payload.get("today") else None
    try:
        return rails_service.submit(
            db, payload,
            idempotency_key=request.headers.get("Idempotency-Key"),
            signature=request.headers.get("X-JWS-Signature"),
            secret=RAILS_SECRET, today=today)
    except rails_service.RailsError as e:
        raise HTTPException(status_code=e.status, detail=e.detail)


@router.get("/claims/{submission_id}")
def get_submission(submission_id: str, db: Session = Depends(get_db)) -> dict:
    out = rails_service.get_submission(db, submission_id)
    if out is None:
        raise HTTPException(status_code=404, detail="submission not found")
    return out
