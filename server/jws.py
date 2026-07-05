"""Detached JWS over canonical JSON (HS256, stdlib — no external dep).

The signature covers a canonical (sorted-key, whitespace-free) rendering of the JSON body, so it
survives HTTP re-serialisation: both sides canonicalise identically. Token form is
`base64url(header)..base64url(mac)` — the doubled dot marks the payload as detached (RFC 7797
style). ES256 + a JWKS endpoint would slot in behind the same interface for production.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
from typing import Optional


def _b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _b64u_dec(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def canonical(obj) -> bytes:
    return json.dumps(obj, separators=(",", ":"), sort_keys=True).encode()


def sign_detached(header: dict, body_obj, secret: str) -> str:
    h = _b64u(canonical(header))
    b = _b64u(canonical(body_obj))
    mac = hmac.new(secret.encode(), f"{h}.{b}".encode(), hashlib.sha256).digest()
    return f"{h}..{_b64u(mac)}"                       # detached: payload omitted between the dots


def verify_detached(token: str, body_obj, secret: str) -> Optional[dict]:
    """Return the decoded protected header if the signature is valid over body_obj, else None."""
    try:
        h, empty, m = token.split(".")
    except (ValueError, AttributeError):
        return None
    if empty != "":                                  # must be the detached (..) form
        return None
    b = _b64u(canonical(body_obj))
    expected = hmac.new(secret.encode(), f"{h}.{b}".encode(), hashlib.sha256).digest()
    try:
        if not hmac.compare_digest(_b64u_dec(m), expected):
            return None
        return json.loads(_b64u_dec(h))
    except Exception:
        return None
