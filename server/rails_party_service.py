"""The register of parties allowed onto the rails channel — ADMIN-maintained, audit-logged.

A party is a provider's own system or a switch. Registering one records its PUBLIC ES256 key and
the provider ids it may act for. The Fund never holds, generates or sees a party's private key:
the party generates its key pair (the conformance kit has a `keygen`) and sends the public half.
"""
from __future__ import annotations

import json
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import jws, models
from .admin_service import AdminError, _audit

KINDS = {"PROVIDER", "SWITCH"}
STATUSES = {"ACTIVE", "SUSPENDED"}
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-]{2,63}$")
MAX_PROVIDERS = 2000


def _out(p: "models.RailsParty") -> dict:
    return {"party_id": p.party_id, "name": p.name, "kind": p.kind, "providers": list(p.providers or []),
            "status": p.status, "key_thumbprint": jws.thumbprint(p.public_jwk),
            "created_by": p.created_by, "created_at": p.created_at.isoformat() if p.created_at else None}


def _providers(kind: str, providers) -> list[str]:
    if not isinstance(providers, list) or not providers or len(providers) > MAX_PROVIDERS:
        raise AdminError(f"providers must be a list of 1 to {MAX_PROVIDERS} provider ids")
    clean = sorted({str(x).strip() for x in providers})
    if any(not x or len(x) > 64 for x in clean):
        raise AdminError("each provider id must be 1 to 64 characters")
    if "*" in clean and (kind != "SWITCH" or len(clean) > 1):
        raise AdminError('"*" (any provider) is for a SWITCH only, and stands alone')
    return clean


def _key(public_jwk) -> dict:
    if isinstance(public_jwk, str):
        try:
            public_jwk = json.loads(public_jwk)
        except ValueError:
            raise AdminError("the public key must be a JWK (JSON)") from None
    try:
        return jws.clean_public_jwk(public_jwk)
    except ValueError as e:
        raise AdminError(str(e)) from None


def _get(db: Session, party_id: str) -> "models.RailsParty":
    p = db.get(models.RailsParty, party_id)
    if p is None:
        raise AdminError(f"no such party: {party_id}")
    return p


def list_parties(db: Session) -> list[dict]:
    return [_out(p) for p in db.scalars(select(models.RailsParty).order_by(models.RailsParty.party_id))]


def register(db: Session, user: dict, party_id: str, name: str, kind: str, providers, public_jwk) -> dict:
    party_id = str(party_id or "").strip()
    if not _ID.match(party_id):
        raise AdminError("party id must be 3 to 64 letters, digits, dots, dashes or underscores")
    if kind not in KINDS:
        raise AdminError(f"kind must be one of {sorted(KINDS)}")
    if db.get(models.RailsParty, party_id) is not None:
        raise AdminError(f"party {party_id} is already registered — rotate its key instead")
    p = models.RailsParty(party_id=party_id, name=str(name or "").strip()[:200], kind=kind,
                          providers=_providers(kind, providers), public_jwk=_key(public_jwk),
                          status="ACTIVE", created_by=user["username"])
    db.add(p)
    _audit(db, user, "rails_party.register", party_id, {"kind": kind, "providers": p.providers})
    db.commit()
    return _out(p)


def set_status(db: Session, user: dict, party_id: str, status: str) -> dict:
    p = _get(db, party_id)
    if status not in STATUSES:
        raise AdminError(f"status must be one of {sorted(STATUSES)}")
    p.status = status
    _audit(db, user, "rails_party.status", party_id, {"status": status})
    db.commit()
    return _out(p)


def set_providers(db: Session, user: dict, party_id: str, providers) -> dict:
    p = _get(db, party_id)
    p.providers = _providers(p.kind, providers)
    _audit(db, user, "rails_party.providers", party_id, {"providers": p.providers})
    db.commit()
    return _out(p)


def rotate_key(db: Session, user: dict, party_id: str, public_jwk) -> dict:
    """Replace the party's public key. Signatures under the old key stop verifying at once."""
    p = _get(db, party_id)
    old = jws.thumbprint(p.public_jwk)
    p.public_jwk = _key(public_jwk)
    _audit(db, user, "rails_party.rotate_key", party_id,
           {"old_thumbprint": old, "new_thumbprint": jws.thumbprint(p.public_jwk)})
    db.commit()
    return _out(p)
