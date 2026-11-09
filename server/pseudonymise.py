"""POPIA pseudonymisation at ingest (SPECIFICATION §4/§9, domain-logic §2).

Raw personal identifiers (a national ID) are HMAC-SHA256 pseudonymised into a stable party token
(P_*) at the ingest boundary, and raw PII is never persisted. The token is deterministic, so the
same person maps to the same P_* across claims (party-recurrence / accident-graph signals depend
on this). Backward compatible: a payload that already carries a pseudonymous party_token passes
through unchanged (its PII fields still stripped).

Three layers, applied at EVERY depth of the payload (not only its top level):
  1. the engine-facing structures (`lines`, `undertaking`, its `authorisations`) are reduced to
     their declared fields — a `patient_name` smuggled inside a billing line is dropped;
  2. any key that names a person (id numbers, names, contact details, dates of birth) is dropped
     wherever it appears, including inside the free-form extras a payload may carry;
  3. any string value that looks like a raw SA identity number (13 digits) is replaced by its
     P_* token wherever it appears, so an identifier under an unexpected key is still never stored.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import re

from .config import PSEUDONYM_SECRET

# Raw personal-information fields that must never be persisted — stripped at every depth.
PII_FIELDS = ("id_number", "national_id", "party_id", "claimant_id", "claimant_name",
              "patient_name", "claimant_surname")
# Key fragments that name a person or their contact details — dropped at every depth.
PII_KEY_PATTERN = re.compile(
    r"(^|_)(id_number|national_id|passport|surname|first_?name|last_?name|full_?name|initials|"
    r"email|phone|cell|mobile|tel|address|street|postal|dob|date_of_birth|birth)(_|$)|_name$|^name$",
    re.IGNORECASE)
RAW_SA_ID = re.compile(r"^\d{13}$")

# The engine-facing structures carry exactly their declared fields (server.validation contract).
LINE_FIELDS = frozenset({"kind", "code", "qty", "amount", "service_date", "provider_id", "dx",
                         "discipline", "emergency", "scheme_paid"})
UNDERTAKING_FIELDS = frozenset({"active", "scope_dx", "scope_coded", "authorisations"})
AUTHORISATION_FIELDS = frozenset({"codes", "qty_limit", "ceiling", "valid_from", "valid_to", "status"})


def token(raw: str, prefix: str = "P", secret: str = PSEUDONYM_SECRET) -> str:
    """Stable HMAC-SHA256 pseudonym of a raw identifier -> '<prefix>_<base32-16>'."""
    digest = hmac.new(secret.encode(), str(raw).strip().encode(), hashlib.sha256).digest()
    return f"{prefix}_{base64.b32encode(digest).decode().rstrip('=')[:16].lower()}"


def _pii_key(key) -> bool:
    k = str(key)
    return k in PII_FIELDS or bool(PII_KEY_PATTERN.search(k))


def _scrub(value, *, allow: frozenset | None = None):
    """Recursively drop PII-named keys, reduce typed structures to their fields and tokenise any
    raw SA identity number found as a value."""
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if _pii_key(k) or (allow is not None and k not in allow):
                continue
            if k == "lines" and isinstance(v, list):
                out[k] = [_scrub(l, allow=LINE_FIELDS) if isinstance(l, dict) else _scrub(l) for l in v]
            elif k == "undertaking" and isinstance(v, dict):
                out[k] = _scrub(v, allow=UNDERTAKING_FIELDS)
            elif k == "authorisations" and isinstance(v, list):
                out[k] = [_scrub(a, allow=AUTHORISATION_FIELDS) if isinstance(a, dict) else _scrub(a)
                          for a in v]
            else:
                out[k] = _scrub(v)
        return out
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    if isinstance(value, str) and RAW_SA_ID.match(value.strip()):
        return token(value, "P")
    return value


def pseudonymise_ingest(payload: dict) -> dict:
    """Return a copy of the payload with the party token derived from any raw national ID and all
    raw PII removed at every depth. Idempotent — an already-tokenised payload passes through."""
    p = dict(payload)
    raw_id = p.get("id_number") or p.get("national_id") or p.get("party_id") or p.get("claimant_id")
    if raw_id and not p.get("party_token"):
        p["party_token"] = token(raw_id, "P")
    party_token = p.get("party_token")                 # validated separately (a raw ID there is 422)
    p = _scrub(p)
    if party_token is not None:
        p["party_token"] = party_token
    return p
