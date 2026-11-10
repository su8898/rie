"""Who is calling the rails channel, and for which providers may they act.

Ported from CIE's interface standard (§3.4 signing, §3.3 asserted provider). A connecting party
— a provider's own system, or a switch acting for many — signs every request with its own ES256
private key and names the key in the JWS header (`kid`). The Fund verifies with the public key
it registered for that party, so the signature identifies the signer, and then checks that the
party may act for the provider the request concerns.

The older shared HS256 secret still verifies when it is enabled (dev, test, the legacy client).
It identifies nobody — any holder may act for any provider — so production leaves it off.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from . import config, jws, models

MAX_LIFETIME = 900                                   # seconds an ES256 signature may stay valid
LEGACY_PARTY = "shared-secret"


@dataclass(frozen=True)
class Caller:
    party_id: str
    kind: str                                        # PROVIDER | SWITCH | LEGACY
    alg: str
    providers: Optional[frozenset] = None            # None = may act for any provider

    def may_act_for(self, provider_id: str) -> bool:
        return self.providers is None or provider_id in self.providers

    def may_act_for_any(self, provider_ids) -> bool:
        return any(self.may_act_for(p) for p in provider_ids)


class AuthError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


_BAD = "invalid or missing JWS signature"


def authenticate(db: Session, token: Optional[str], obj) -> tuple[Caller, dict]:
    """Verify a detached JWS over `obj` and say who signed it. Raises AuthError(401)."""
    header = jws.peek_header(token or "")
    if header is None:
        raise AuthError(401, _BAD)
    now = time.time()
    if header.get("alg") == "ES256":
        party = db.get(models.RailsParty, str(header.get("kid") or ""))
        if party is None or party.status != "ACTIVE":
            raise AuthError(401, "unknown or suspended signing key")
        if jws.verify_es256(token, obj, party.public_jwk) is None:
            raise AuthError(401, _BAD)
        try:
            exp = float(header["exp"])
        except (KeyError, TypeError, ValueError):
            raise AuthError(401, "exp (expiry) required in the JWS header") from None
        if exp < now:
            raise AuthError(401, "signature expired")
        if exp > now + MAX_LIFETIME:
            raise AuthError(401, f"exp is more than {MAX_LIFETIME} seconds ahead")
        providers = None if "*" in (party.providers or []) else frozenset(party.providers or [])
        return Caller(party.party_id, party.kind, "ES256", providers), header
    if header.get("alg") == "HS256" and config.RAILS_SHARED_SECRET_ENABLED:
        if jws.verify_detached(token, obj, config.RAILS_SECRET) is None:
            raise AuthError(401, _BAD)
        if header.get("exp") and float(header["exp"]) < now:
            raise AuthError(401, "signature expired")
        return Caller(LEGACY_PARTY, "LEGACY", "HS256"), header
    raise AuthError(401, _BAD)


# ── the Fund's own signing key ───────────────────────────────────────────────
_fund: dict = {}


def fund_key():
    """(private key, kid). From RIE_RAILS_SIGNING_KEY when set, else generated once per process."""
    if not _fund:
        key = (jws.load_private_key(config.RAILS_SIGNING_KEY_PEM) if config.RAILS_SIGNING_KEY_PEM
               else jws.generate_key())
        _fund["key"], _fund["kid"] = key, jws.thumbprint(jws.public_jwk(key))
    return _fund["key"], _fund["kid"]


def jwks() -> dict:
    """The Fund's public signing key, as published for parties to verify receipts against."""
    key, kid = fund_key()
    return {"keys": [jws.public_jwk(key, kid)]}


def sign_for(caller: Caller, body: dict) -> str:
    """The Fund's signature on a response: ES256 under its own key for a registered party, or
    the shared secret for a legacy caller (who has no other way to verify)."""
    if caller.alg == "ES256":
        key, kid = fund_key()
        return jws.sign_detached({"alg": "ES256", "kid": kid, "iss": "RAF-RIE"}, body, key)
    return jws.sign_detached({"alg": "HS256", "iss": "RAF-RIE"}, body, config.RAILS_SECRET)
