"""Provider->fund submission rails — the Core Rails round-trip (CIE conformance analog).

A provider signs an RCJ claim (detached JWS over the canonical body) and POSTs it with an
Idempotency-Key. The fund: verifies the signature, rejects replays (one-time jti), enforces
idempotency (same key+body -> the same verdict; same key+different body -> 409), scores the claim
through the engine (persisting it to the corpus), and returns a signed Verdict + Receipt.
"""
from __future__ import annotations

import hashlib
import time
import uuid
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from . import jws, models, rails_auth
from .pipeline_service import DuplicateClaim, assess_and_store
from .pseudonymise import pseudonymise_ingest
from .validation import SubmissionError, validate_submission

_NS = uuid.UUID("1b671a64-40d5-491e-99b0-da01ff1f3341")   # idempotency-key -> submission_id

# Facts only the FUND may assert. A provider's submission never carries them: payee verification,
# standing, merits, serious-injury, prescription suspension, fault, life status, undertakings and
# the assessment clock are fund-side determinations (SPECIFICATION §4/§8e). Anything here is
# dropped before scoring, so a provider cannot self-attest its way past a payment gate.
FUND_ONLY_FIELDS = (
    "payee_verified", "provider_registered", "attorney_in_standing", "merits_accepted",
    "merits_ground", "si_accepted", "prescription_suspended", "fault_pct", "claimant_deceased_on",
    "undertaking", "summons_served", "today", "provider_tier", "cohort_is_bus_taxi", "conv_floor_p10",
)


def strip_fund_fields(body: dict) -> dict:
    return {k: v for k, v in body.items() if k not in FUND_ONLY_FIELDS}


class RailsError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def _body_hash(body: dict) -> str:
    return hashlib.sha256(jws.canonical(body)).hexdigest()


def _verdict(body: dict, record: dict) -> dict:
    billed = round(sum(float(l["amount"]) for l in body.get("lines", [])), 2)
    disp = record["disposition"]
    outcome = ("CLEAN_PASS" if disp == "CLEAN" else "REPRICED" if disp == "ADJUSTED" else "HELD")
    return {
        "outcome": outcome,
        "billed": billed,
        "payableNow": record["net_payable"],
        "repricedOff": round(max(0.0, billed - record["medical_payable"]), 2),
        "band": record["band"], "score": record["score"], "disposition": disp,
        "reasons": record["reasons"], "holds": record["holds"],
        "claimId": record["claim_id"], "accidentId": record["accident_id"],
        "engineVersion": record["engine_version"],
    }


def _receipt(submission_id: str, verdict: dict, caller: "rails_auth.Caller") -> dict:
    body = {"submissionId": submission_id, "outcome": verdict["outcome"],
            "payableNow": verdict["payableNow"], "receivedAt": int(time.time())}
    return {**body, "signature": rails_auth.sign_for(caller, body)}       # the Fund signs


def authenticate_write(db: Session, body, signature: Optional[str]) -> tuple["rails_auth.Caller", str]:
    """A provider write: a valid signature over the body and a one-time jti not seen before.
    Returns the caller and the jti; the caller of this function records the jti once it commits."""
    try:
        caller, header = rails_auth.authenticate(db, signature, body)
    except rails_auth.AuthError as e:
        raise RailsError(e.status, e.detail) from None
    jti = header.get("jti")
    if not jti:
        raise RailsError(400, "jti (one-time nonce) required in the JWS header")
    return caller, str(jti)


def check_scope(caller: "rails_auth.Caller", body: dict) -> None:
    """Every line on the claim must be billed by a provider this party may act for."""
    for provider_id in sorted({l["provider_id"] for l in body.get("lines", [])}):
        if not caller.may_act_for(provider_id):
            raise RailsError(403, f"this signing key may not act for provider {provider_id}")


def submit(db: Session, body: dict, idempotency_key: Optional[str], signature: Optional[str],
           today: Optional[date] = None) -> dict:
    if not idempotency_key:
        raise RailsError(400, "Idempotency-Key header required")
    caller, jti = authenticate_write(db, body, signature)
    return submit_as(db, caller, jti, body, idempotency_key, today=today)


def submit_as(db: Session, caller: "rails_auth.Caller", jti: str, body: dict, idempotency_key: str,
              today: Optional[date] = None, claim: Optional[dict] = None) -> dict:
    """Score one claim for an authenticated caller. `body` is what was signed (it fixes the
    idempotency hash); `claim` is the claim to score when it differs from the body — a switch
    message is signed as a wrapper and scored as the claim parsed out of it."""
    submission_id = str(uuid.uuid5(_NS, idempotency_key))
    existing = db.get(models.RailsSubmission, submission_id)
    body_hash = _body_hash(body)
    if existing is not None:                                  # idempotent replay
        if existing.party_id not in (None, caller.party_id):
            raise RailsError(409, "Idempotency-Key was used by another party")
        if existing.body_hash == body_hash:
            return {"submissionId": submission_id, "verdict": existing.verdict,
                    "receipt": existing.receipt, "idempotentReplay": True}
        raise RailsError(409, "Idempotency-Key reused with a different body")

    if db.get(models.RailsSeenJti, jti) is not None:          # replay guard
        raise RailsError(409, "replay detected: jti already used")
    # POPIA + fund-only facts dropped (§2, §8e)
    body = strip_fund_fields(pseudonymise_ingest(claim if claim is not None else body))
    try:
        body = validate_submission(body)
    except SubmissionError as e:
        raise RailsError(422, f"invalid claim: {e}")
    check_scope(caller, body)
    if db.get(models.ClaimRecord, body["claim_id"]) is not None:
        raise RailsError(409, f"claim {body['claim_id']} already submitted")

    db.add(models.RailsSeenJti(jti=jti))
    try:
        record = assess_and_store(db, body, today=today)      # score + persist to the corpus
    except DuplicateClaim as e:
        db.rollback()
        raise RailsError(409, str(e))
    verdict = _verdict(body, record)
    receipt = _receipt(submission_id, verdict, caller)
    db.add(models.RailsSubmission(
        submission_id=submission_id, party_id=caller.party_id,
        idempotency_key=idempotency_key, body_hash=body_hash,
        claim_id=body["claim_id"], outcome=verdict["outcome"], verdict=verdict, receipt=receipt))
    db.commit()
    return {"submissionId": submission_id, "verdict": verdict, "receipt": receipt}


def get_submission(db: Session, submission_id: str) -> Optional[dict]:
    s = db.get(models.RailsSubmission, submission_id)
    if s is None:
        return None
    return {"submissionId": s.submission_id, "claimId": s.claim_id, "outcome": s.outcome,
            "verdict": s.verdict, "receipt": s.receipt}
