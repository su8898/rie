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

from . import jws, models
from .config import RAILS_SECRET
from .pipeline_service import assess_and_store
from .pseudonymise import pseudonymise_ingest

_NS = uuid.UUID("1b671a64-40d5-491e-99b0-da01ff1f3341")   # idempotency-key -> submission_id
_REQUIRED = ("claim_id", "claim_type", "party_token", "accident_date", "lodged_on")


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


def _receipt(submission_id: str, verdict: dict, secret: str) -> dict:
    body = {"submissionId": submission_id, "outcome": verdict["outcome"],
            "payableNow": verdict["payableNow"], "receivedAt": int(time.time())}
    sig = jws.sign_detached({"alg": "HS256", "iss": "RAF-RIE"}, body, secret)   # fund signs
    return {**body, "signature": sig}


def submit(db: Session, body: dict, idempotency_key: Optional[str], signature: Optional[str],
           secret: str = RAILS_SECRET, today: Optional[date] = None) -> dict:
    if not idempotency_key:
        raise RailsError(400, "Idempotency-Key header required")
    header = jws.verify_detached(signature or "", body, secret)
    if header is None:
        raise RailsError(401, "invalid or missing JWS signature")
    if header.get("exp") and float(header["exp"]) < time.time():
        raise RailsError(401, "signature expired")
    jti = header.get("jti")
    if not jti:
        raise RailsError(400, "jti (one-time nonce) required in the JWS header")

    submission_id = str(uuid.uuid5(_NS, idempotency_key))
    existing = db.get(models.RailsSubmission, submission_id)
    body_hash = _body_hash(body)
    if existing is not None:                                  # idempotent replay
        if existing.body_hash == body_hash:
            return {"submissionId": submission_id, "verdict": existing.verdict,
                    "receipt": existing.receipt, "idempotentReplay": True}
        raise RailsError(409, "Idempotency-Key reused with a different body")

    if db.get(models.RailsSeenJti, jti) is not None:          # replay guard
        raise RailsError(409, "replay detected: jti already used")
    body = pseudonymise_ingest(body)                          # POPIA — after JWS verify, before persist (§2)
    if [k for k in _REQUIRED if k not in body]:
        raise RailsError(422, "missing required claim fields")

    db.add(models.RailsSeenJti(jti=jti))
    record = assess_and_store(db, body, today=today)          # score + persist to the corpus
    verdict = _verdict(body, record)
    receipt = _receipt(submission_id, verdict, secret)
    db.add(models.RailsSubmission(
        submission_id=submission_id, idempotency_key=idempotency_key, body_hash=body_hash,
        claim_id=body["claim_id"], outcome=verdict["outcome"], verdict=verdict, receipt=receipt))
    db.commit()
    return {"submissionId": submission_id, "verdict": verdict, "receipt": receipt}


def get_submission(db: Session, submission_id: str) -> Optional[dict]:
    s = db.get(models.RailsSubmission, submission_id)
    if s is None:
        return None
    return {"submissionId": s.submission_id, "outcome": s.outcome,
            "verdict": s.verdict, "receipt": s.receipt}
