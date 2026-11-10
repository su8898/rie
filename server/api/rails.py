"""Provider->fund rails endpoints (JWS-authenticated, not the operator session).

Every request is signed. A registered party signs with its own ES256 key and names it in the JWS
header (`kid`); the Fund verifies with the public key it holds for that party and then checks
that the party may act for the provider the request concerns. A POST is signed over its body. A
GET is signed over the request's own subject, e.g. `{"submissionId": id}` or `{"providerId": id}`.
An operator with a session may make the same reads. Nothing here is public except the Fund's own
public key (the JWKS), which parties need in order to verify its receipts.

Beyond claim submission the channel carries the profiles ported from CIE's interface standard:
switch messages, batches, claim status, registration lookup, remittance advice, objections and
medical reports."""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from .. import (
    medical_report_service, models, provider_service, rails_auth, rails_batch_service,
    rails_service, remittance_service, switch_intake,
)
from ..db import get_db
from .deps import current_user

router = APIRouter(prefix="/rails/v1")
Caller = rails_auth.Caller


# ── who is calling ───────────────────────────────────────────────────────────
def _signed(request: Request, db: Session, obj) -> Caller:
    try:
        return rails_auth.authenticate(db, request.headers.get("X-JWS-Signature"), obj)[0]
    except rails_auth.AuthError as e:
        raise HTTPException(status_code=e.status, detail=e.detail) from None


def _require(request: Request, db: Session, obj: dict, what: str) -> Optional[Caller]:
    """A read is for a party (a JWS over `obj`, the request's own subject) or an operator with a
    session. Returns the party, or None for an operator, who is not provider-scoped."""
    if request.headers.get("X-JWS-Signature"):
        return _signed(request, db, obj)
    try:
        current_user(request, db)
    except HTTPException:
        raise HTTPException(status_code=401,
                            detail=f"JWS signature over {what} or operator session required") from None
    return None


def _write(request: Request, db: Session, body) -> Caller:
    """A party write: signed over its body, unexpired, carrying a one-time jti not seen before."""
    try:
        caller, jti = rails_service.authenticate_write(db, body, request.headers.get("X-JWS-Signature"))
    except rails_service.RailsError as e:
        raise HTTPException(status_code=e.status, detail=e.detail) from None
    if db.get(models.RailsSeenJti, jti) is not None:
        raise HTTPException(status_code=409, detail="replay detected: jti already used")
    db.add(models.RailsSeenJti(jti=jti))
    return caller


def _for_provider(caller: Optional[Caller], provider_id: str) -> None:
    """The request names a provider outright: the party must be allowed to act for it."""
    if caller is not None and not caller.may_act_for(provider_id):
        raise HTTPException(status_code=403,
                            detail=f"this signing key may not act for provider {provider_id}")


def _owns(caller: Optional[Caller], provider_ids, missing: str) -> None:
    """The request names a record by reference: one a party may not see looks like one that
    does not exist."""
    if caller is not None and not caller.may_act_for_any(provider_ids):
        raise HTTPException(status_code=404, detail=missing)


def _call(fn, *args, **kw):
    try:
        return fn(*args, **kw)
    except (provider_service.ProviderError, remittance_service.RemittanceError,
            medical_report_service.ReportError, rails_service.RailsError,
            rails_batch_service.BatchError, switch_intake.SwitchError) as e:
        raise HTTPException(status_code=e.status, detail=e.detail) from None


@router.get("/.well-known/jwks.json")
def jwks() -> dict:
    return rails_auth.jwks()


# ── claims ───────────────────────────────────────────────────────────────────
@router.post("/claims")
def submit(request: Request, payload: dict = Body(...), db: Session = Depends(get_db)) -> dict:
    return _call(rails_service.submit, db, payload,
                 idempotency_key=request.headers.get("Idempotency-Key"),
                 signature=request.headers.get("X-JWS-Signature"))   # the fund's clock, never the provider's


@router.post("/claims/switch")
def submit_switch_message(request: Request, payload: dict = Body(...),
                          db: Session = Depends(get_db)) -> dict:
    return _call(switch_intake.submit, db, payload,
                 idempotency_key=request.headers.get("Idempotency-Key"),
                 signature=request.headers.get("X-JWS-Signature"))


@router.post("/batches")
def submit_batch(request: Request, payload: dict = Body(...), db: Session = Depends(get_db)) -> dict:
    return _call(rails_batch_service.submit, db, payload,
                 idempotency_key=request.headers.get("Idempotency-Key"),
                 signature=request.headers.get("X-JWS-Signature"))


@router.get("/batches/{batch_id}")
def get_batch(batch_id: str, request: Request, db: Session = Depends(get_db)) -> dict:
    caller = _require(request, db, {"batchId": batch_id}, "{batchId}")
    return _call(rails_batch_service.get, db, batch_id, caller)


@router.get("/claims/{submission_id}")
def get_submission(submission_id: str, request: Request, db: Session = Depends(get_db)) -> dict:
    caller = _require(request, db, {"submissionId": submission_id}, "{submissionId}")
    out = rails_service.get_submission(db, submission_id)
    if out is None:
        raise HTTPException(status_code=404, detail="submission not found")
    _owns(caller, provider_service.claim_providers(db, out["claimId"]), "submission not found")
    return out


# ── claim status ─────────────────────────────────────────────────────────────
@router.get("/status/{claim_id}")
def claim_status(claim_id: str, request: Request, db: Session = Depends(get_db)) -> dict:
    caller = _require(request, db, {"claimId": claim_id}, "{claimId}")
    _owns(caller, provider_service.claim_providers(db, claim_id), "claim not found")
    return _call(provider_service.claim_status, db, claim_id)


# ── registration lookup (the body carries an identity number, so it is a signed POST) ──
@router.post("/registration/lookup")
def registration_lookup(request: Request, payload: dict = Body(...),
                        db: Session = Depends(get_db)) -> dict:
    _signed(request, db, payload)                     # any registered party may ask
    return _call(provider_service.registration_lookup, db, payload)


# ── remittance advice ────────────────────────────────────────────────────────
@router.get("/remittances")
def remittances(provider_id: str, request: Request, date_from: Optional[date] = None,
                date_to: Optional[date] = None, db: Session = Depends(get_db)) -> list[dict]:
    _for_provider(_require(request, db, {"providerId": provider_id}, "{providerId}"), provider_id)
    return remittance_service.list_remittances(db, provider_id, date_from, date_to)


@router.get("/remittances/{ref}")
def remittance(ref: str, request: Request, format: str = "json", db: Session = Depends(get_db)):
    caller = _require(request, db, {"remittanceRef": ref}, "{remittanceRef}")
    detail = _call(remittance_service.detail, db, ref)
    _owns(caller, [detail["provider_id"]], "remittance not found")
    if format == "xml":
        return Response(content=remittance_service.to_xml(detail), media_type="application/xml")
    return detail


@router.post("/remittances/{ref}/ack")
def acknowledge_remittance(ref: str, request: Request, db: Session = Depends(get_db)) -> dict:
    caller = _signed(request, db, {"remittanceRef": ref})
    _owns(caller, [_call(remittance_service.detail, db, ref)["provider_id"]], "remittance not found")
    return _call(remittance_service.acknowledge, db, ref)


# ── objections ───────────────────────────────────────────────────────────────
@router.post("/objections")
def lodge_objection(request: Request, payload: dict = Body(...), db: Session = Depends(get_db)) -> dict:
    _for_provider(_write(request, db, payload), str(payload.get("provider_id") or ""))
    return _call(provider_service.lodge_objection, db, payload)


@router.get("/objections")
def objections(provider_id: str, request: Request, db: Session = Depends(get_db)) -> list[dict]:
    _for_provider(_require(request, db, {"providerId": provider_id}, "{providerId}"), provider_id)
    return provider_service.list_objections(db, provider_id)


@router.get("/objections/{ref}")
def objection(ref: str, request: Request, db: Session = Depends(get_db)) -> dict:
    caller = _require(request, db, {"objectionRef": ref}, "{objectionRef}")
    out = _call(provider_service.get_objection, db, ref)
    _owns(caller, [out["providerId"]], "objection not found")
    return out


# ── medical reports (RAF 1 medical report, RAF 4) ────────────────────────────
@router.get("/medical-reports/forms")
def medical_report_forms(request: Request, db: Session = Depends(get_db)) -> list[dict]:
    _require(request, db, {"catalogue": "medical-report-forms"}, '{"catalogue": "medical-report-forms"}')
    return medical_report_service.catalogue()


@router.post("/medical-reports")
def file_medical_report(request: Request, payload: dict = Body(...), db: Session = Depends(get_db)) -> dict:
    _for_provider(_write(request, db, payload), str(payload.get("provider_id") or ""))
    return _call(medical_report_service.receive, db, payload, request.headers.get("Idempotency-Key"))


@router.get("/medical-reports")
def medical_reports(provider_id: str, request: Request, db: Session = Depends(get_db)) -> list[dict]:
    _for_provider(_require(request, db, {"providerId": provider_id}, "{providerId}"), provider_id)
    return medical_report_service.list_reports(db, provider_id=provider_id)


@router.get("/medical-reports/{ref}")
def medical_report(ref: str, request: Request, format: str = "json", db: Session = Depends(get_db)):
    caller = _require(request, db, {"reportRef": ref}, "{reportRef}")
    detail = _call(medical_report_service.get, db, ref)
    _owns(caller, [detail["provider_id"]], "medical report not found")
    if format == "xml":
        return Response(content=medical_report_service.to_xml(detail), media_type="application/xml")
    return detail


@router.get("/claims/{claim_id}/documentation")
def claim_documentation(claim_id: str, request: Request, db: Session = Depends(get_db)) -> dict:
    caller = _require(request, db, {"claimId": claim_id}, "{claimId}")
    filed = {r["provider_id"] for r in medical_report_service.list_reports(db, claim_id=claim_id)}
    _owns(caller, provider_service.claim_providers(db, claim_id) | filed, "claim not found")
    return _call(medical_report_service.documentation, db, claim_id)
