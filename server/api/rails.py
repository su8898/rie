"""Provider->fund submission rails endpoints (JWS-authenticated, not the operator session).

POST verifies a detached JWS over the body. GET is for the submitting provider (a JWS over
`{"submissionId": id}`) or an operator with a valid session — verdicts are not public."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import jws, rails_service
from ..config import RAILS_SECRET
from ..db import get_db
from .deps import current_user

router = APIRouter(prefix="/rails/v1")


@router.post("/claims")
def submit(request: Request, payload: dict = Body(...), db: Session = Depends(get_db)) -> dict:
    try:
        return rails_service.submit(
            db, payload,
            idempotency_key=request.headers.get("Idempotency-Key"),
            signature=request.headers.get("X-JWS-Signature"),
            secret=RAILS_SECRET)                       # the fund's clock, never the provider's
    except rails_service.RailsError as e:
        raise HTTPException(status_code=e.status, detail=e.detail)


def _authorised(request: Request, db: Session, submission_id: str) -> bool:
    sig = request.headers.get("X-JWS-Signature")
    if sig and jws.verify_detached(sig, {"submissionId": submission_id}, RAILS_SECRET) is not None:
        return True
    try:
        current_user(request, db)
        return True
    except HTTPException:
        return False


@router.get("/claims/{submission_id}")
def get_submission(submission_id: str, request: Request, db: Session = Depends(get_db)) -> dict:
    if not _authorised(request, db, submission_id):
        raise HTTPException(status_code=401, detail="JWS signature over {submissionId} or operator session required")
    out = rails_service.get_submission(db, submission_id)
    if out is None:
        raise HTTPException(status_code=404, detail="submission not found")
    return out
