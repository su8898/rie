"""Batch submission — a night's claims in one signed request (port of CIE's batch profile).

A batch changes nothing about a verdict: it is `{"claims": [claim, …]}`, each entry the ordinary
rails claim, and each result the ordinary verdict and receipt. It is a reliability envelope.
Partial success is normal — one bad claim does not fail the file — and a resend is safe at two
levels: the same Idempotency-Key and body returns the stored batch, and a claim the same party
already submitted comes back with its stored verdict, marked `deduplicated`.
"""
from __future__ import annotations

import hashlib
import uuid
from collections import Counter
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import jws, models, rails_auth, rails_service

MAX_BATCH = 100
_NS = uuid.UUID("5d0c7c0e-3c1b-4f0a-9a52-6f7a1f0c2b11")


class BatchError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def _stored(db: Session, caller: "rails_auth.Caller", claim_id: str) -> Optional[dict]:
    """This party's earlier submission of the same claim, if there is one."""
    s = db.scalar(select(models.RailsSubmission).where(
        models.RailsSubmission.claim_id == claim_id,
        models.RailsSubmission.party_id == caller.party_id).limit(1))
    return None if s is None else {"submissionId": s.submission_id, "verdict": s.verdict,
                                   "receipt": s.receipt}


def _one(db: Session, caller, jti: str, key: str, index: int, claim) -> dict:
    claim_id = str(claim.get("claim_id") or "") if isinstance(claim, dict) else ""
    out = {"index": index, "claimId": claim_id or None}
    if not isinstance(claim, dict):
        return {**out, "status": 422, "error": "each claim must be an object"}
    earlier = _stored(db, caller, claim_id) if claim_id else None
    if earlier is not None:
        return {**out, "status": 200, "deduplicated": True, **earlier}
    try:
        done = rails_service.submit_as(db, caller, f"{jti}:{index}", claim, f"{key}:{index}")
    except rails_service.RailsError as e:
        db.rollback()
        return {**out, "status": e.status, "error": e.detail}
    return {**out, "status": 200, "deduplicated": False, "submissionId": done["submissionId"],
            "verdict": done["verdict"], "receipt": done["receipt"]}


def _dict(b: "models.RailsBatch", replay: bool) -> dict:
    return {"batchId": b.batch_id, "claims": b.n_claims, "summary": b.summary, "results": b.results,
            "receivedAt": b.created_at.isoformat() if b.created_at else None, "idempotentReplay": replay}


def submit(db: Session, payload: dict, idempotency_key: Optional[str], signature: Optional[str]) -> dict:
    if not idempotency_key:
        raise BatchError(400, "Idempotency-Key header required")
    try:
        caller, jti = rails_service.authenticate_write(db, payload, signature)
    except rails_service.RailsError as e:
        raise BatchError(e.status, e.detail) from None
    claims = payload.get("claims")
    if not isinstance(claims, list) or not 1 <= len(claims) <= MAX_BATCH:
        raise BatchError(422, f"claims must be a list of 1 to {MAX_BATCH} claims")

    batch_id = str(uuid.uuid5(_NS, idempotency_key))
    body_hash = hashlib.sha256(jws.canonical(payload)).hexdigest()
    existing = db.get(models.RailsBatch, batch_id)
    if existing is not None:
        if existing.party_id != caller.party_id or existing.body_hash != body_hash:
            raise BatchError(409, "Idempotency-Key reused by another party or with a different body")
        return _dict(existing, replay=True)
    if db.get(models.RailsSeenJti, jti) is not None:
        raise BatchError(409, "replay detected: jti already used")

    results = [_one(db, caller, jti, idempotency_key, i, c) for i, c in enumerate(claims)]
    outcomes = Counter(r["verdict"]["outcome"] if r["status"] == 200 else "REJECTED" for r in results)
    batch = models.RailsBatch(
        batch_id=batch_id, idempotency_key=idempotency_key, body_hash=body_hash,
        party_id=caller.party_id, n_claims=len(claims), results=results,
        summary={**dict(outcomes), "deduplicated": sum(1 for r in results if r.get("deduplicated"))})
    db.add(batch)
    db.add(models.RailsSeenJti(jti=jti))
    db.commit()
    return _dict(batch, replay=False)


def get(db: Session, batch_id: str, caller: Optional["rails_auth.Caller"]) -> dict:
    """A batch is read back by the party that sent it, or by an operator (caller None)."""
    b = db.get(models.RailsBatch, batch_id)
    if b is None or (caller is not None and caller.party_id != b.party_id):
        raise BatchError(404, "batch not found")
    return _dict(b, replay=False)
