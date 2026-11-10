"""Provider->fund rails endpoints (JWS-authenticated, not the operator session).

A POST verifies a detached JWS over its body. A GET is for the provider (a JWS over the request's
own subject, e.g. `{"submissionId": id}` or `{"providerId": id}`) or an operator with a valid
session — nothing here is public. Beyond claim submission the channel carries the provider
lookups ported from CIE's interface standard: claim status, registration lookup, remittance
advice and objections."""
from __future__ import annotations

import time
from datetime import date
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from .. import jws, models, provider_service, rails_service, remittance_service
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


def _signed(request: Request, obj: dict) -> Optional[dict]:
    """The JWS header if the request carries a valid, unexpired detached signature over `obj`."""
    header = jws.verify_detached(request.headers.get("X-JWS-Signature") or "", obj, RAILS_SECRET)
    if header is None or (header.get("exp") and float(header["exp"]) < time.time()):
        return None
    return header


def _require(request: Request, db: Session, obj: dict, what: str) -> None:
    """A read is for the provider (a JWS over `obj`, the request's own subject) or an operator
    with a session — nothing on this channel is public."""
    if _signed(request, obj) is not None:
        return
    try:
        current_user(request, db)
    except HTTPException:
        raise HTTPException(status_code=401,
                            detail=f"JWS signature over {what} or operator session required") from None


def _write(request: Request, db: Session, body: dict) -> None:
    """A provider write: signed over its body, unexpired, and carrying a one-time jti."""
    header = _signed(request, body)
    if header is None:
        raise HTTPException(status_code=401, detail="invalid, expired or missing JWS signature")
    jti = header.get("jti")
    if not jti:
        raise HTTPException(status_code=400, detail="jti (one-time nonce) required in the JWS header")
    if db.get(models.RailsSeenJti, jti) is not None:
        raise HTTPException(status_code=409, detail="replay detected: jti already used")
    db.add(models.RailsSeenJti(jti=jti))


def _provider(fn, *args):
    try:
        return fn(*args)
    except (provider_service.ProviderError, remittance_service.RemittanceError) as e:
        raise HTTPException(status_code=e.status, detail=e.detail) from None


@router.get("/claims/{submission_id}")
def get_submission(submission_id: str, request: Request, db: Session = Depends(get_db)) -> dict:
    _require(request, db, {"submissionId": submission_id}, "{submissionId}")
    out = rails_service.get_submission(db, submission_id)
    if out is None:
        raise HTTPException(status_code=404, detail="submission not found")
    return out


# ── claim status ─────────────────────────────────────────────────────────────
@router.get("/status/{claim_id}")
def claim_status(claim_id: str, request: Request, db: Session = Depends(get_db)) -> dict:
    _require(request, db, {"claimId": claim_id}, "{claimId}")
    return _provider(provider_service.claim_status, db, claim_id)


# ── registration lookup (the body carries an identity number, so it is a signed POST) ──
@router.post("/registration/lookup")
def registration_lookup(request: Request, payload: dict = Body(...),
                        db: Session = Depends(get_db)) -> dict:
    if _signed(request, payload) is None:
        raise HTTPException(status_code=401, detail="invalid, expired or missing JWS signature")
    return _provider(provider_service.registration_lookup, db, payload)


# ── remittance advice ────────────────────────────────────────────────────────
@router.get("/remittances")
def remittances(provider_id: str, request: Request, date_from: Optional[date] = None,
                date_to: Optional[date] = None, db: Session = Depends(get_db)) -> list[dict]:
    _require(request, db, {"providerId": provider_id}, "{providerId}")
    return remittance_service.list_remittances(db, provider_id, date_from, date_to)


@router.get("/remittances/{ref}")
def remittance(ref: str, request: Request, format: str = "json", db: Session = Depends(get_db)):
    _require(request, db, {"remittanceRef": ref}, "{remittanceRef}")
    detail = _provider(remittance_service.detail, db, ref)
    if format == "xml":
        return Response(content=remittance_service.to_xml(detail), media_type="application/xml")
    return detail


@router.post("/remittances/{ref}/ack")
def acknowledge_remittance(ref: str, request: Request, db: Session = Depends(get_db)) -> dict:
    if _signed(request, {"remittanceRef": ref}) is None:
        raise HTTPException(status_code=401, detail="JWS signature over {remittanceRef} required")
    return _provider(remittance_service.acknowledge, db, ref)


# ── objections ───────────────────────────────────────────────────────────────
@router.post("/objections")
def lodge_objection(request: Request, payload: dict = Body(...), db: Session = Depends(get_db)) -> dict:
    _write(request, db, payload)
    return _provider(provider_service.lodge_objection, db, payload)


@router.get("/objections")
def objections(provider_id: str, request: Request, db: Session = Depends(get_db)) -> list[dict]:
    _require(request, db, {"providerId": provider_id}, "{providerId}")
    return provider_service.list_objections(db, provider_id)


@router.get("/objections/{ref}")
def objection(ref: str, request: Request, db: Session = Depends(get_db)) -> dict:
    _require(request, db, {"objectionRef": ref}, "{objectionRef}")
    return _provider(provider_service.get_objection, db, ref)
