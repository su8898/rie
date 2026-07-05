"""POPIA pseudonymisation at ingest (SPECIFICATION §4/§9, domain-logic §2).

Raw personal identifiers (a national ID) are HMAC-SHA256 pseudonymised into a stable party token
(P_*) at the ingest boundary, and every declared raw-PII field is dropped — raw PII is never
persisted. The token is deterministic, so the same person maps to the same P_* across claims
(party-recurrence / accident-graph signals depend on this). Backward compatible: a payload that
already carries a pseudonymous party_token passes through unchanged (its PII fields still stripped).
"""
from __future__ import annotations

import base64
import hashlib
import hmac

from .config import PSEUDONYM_SECRET

# Raw personal-information fields that must never be persisted — stripped at the ingest boundary.
PII_FIELDS = ("id_number", "national_id", "party_id", "claimant_id", "claimant_name",
              "patient_name", "claimant_surname")


def token(raw: str, prefix: str = "P", secret: str = PSEUDONYM_SECRET) -> str:
    """Stable HMAC-SHA256 pseudonym of a raw identifier -> '<prefix>_<base32-16>'."""
    digest = hmac.new(secret.encode(), str(raw).strip().encode(), hashlib.sha256).digest()
    return f"{prefix}_{base64.b32encode(digest).decode().rstrip('=')[:16].lower()}"


def pseudonymise_ingest(payload: dict) -> dict:
    """Return a copy of the payload with the party token derived from any raw national ID and all
    declared raw-PII fields removed. Idempotent — an already-tokenised payload passes through."""
    p = dict(payload)
    raw_id = p.get("id_number") or p.get("national_id") or p.get("party_id") or p.get("claimant_id")
    if raw_id and not p.get("party_token"):
        p["party_token"] = token(raw_id, "P")
    for f in PII_FIELDS:
        p.pop(f, None)
    return p
