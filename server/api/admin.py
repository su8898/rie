"""ADMIN management surface (SPECIFICATION §6) — users, statutory config, reference tiers,
signal-mode overrides, and the CUD audit log. Every route requires the ADMIN role.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.orm import Session

from .. import admin_service as svc, provider_registry_service as practices, rails_party_service as parties
from ..db import get_db
from .deps import require_role

router = APIRouter(prefix="/admin")
_admin = require_role("ADMIN")


# ── users ──
@router.get("/users")
def users(db: Session = Depends(get_db), user: dict = Depends(_admin)) -> list[dict]:
    return svc.list_users(db)


@router.post("/users")
def create_user(body: dict = Body(...), db: Session = Depends(get_db), user: dict = Depends(_admin)) -> dict:
    return svc.create_user(db, user, body.get("username", ""), body.get("role", ""),
                           body.get("password", ""))


@router.post("/users/{username}/role")
def set_role(username: str, body: dict = Body(...), db: Session = Depends(get_db),
             user: dict = Depends(_admin)) -> dict:
    return svc.set_role(db, user, username, body.get("role", ""))


@router.post("/users/{username}/active")
def set_active(username: str, body: dict = Body(...), db: Session = Depends(get_db),
               user: dict = Depends(_admin)) -> dict:
    return svc.set_active(db, user, username, bool(body.get("active", True)))


@router.post("/users/{username}/password")
def reset_password(username: str, body: dict = Body(...), db: Session = Depends(get_db),
                   user: dict = Depends(_admin)) -> dict:
    return svc.reset_password(db, user, username, body.get("password", ""))


# ── statutory caps ──
@router.get("/caps")
def caps(db: Session = Depends(get_db), user: dict = Depends(_admin)) -> list[dict]:
    return svc.list_caps(db)


@router.post("/caps")
def upsert_cap(body: dict = Body(...), db: Session = Depends(get_db), user: dict = Depends(_admin)) -> dict:
    return svc.upsert_cap(db, user, body.get("effective_from"), body.get("annual_cap"))


@router.delete("/caps/{effective_from}")
def delete_cap(effective_from: str, db: Session = Depends(get_db),
               user: dict = Depends(_admin)) -> dict:
    svc.delete_cap(db, user, effective_from)
    return {"ok": True}


# ── pre-auth + negotiated ──
@router.get("/preauth")
def preauth(db: Session = Depends(get_db), user: dict = Depends(_admin)) -> list[str]:
    return svc.list_preauth(db)


@router.post("/preauth")
def add_preauth(body: dict = Body(...), db: Session = Depends(get_db), user: dict = Depends(_admin)) -> dict:
    svc.add_preauth(db, user, body.get("code", ""))
    return {"ok": True}


@router.delete("/preauth/{code}")
def remove_preauth(code: str, db: Session = Depends(get_db), user: dict = Depends(_admin)) -> dict:
    svc.remove_preauth(db, user, code)
    return {"ok": True}


@router.get("/negotiated")
def negotiated(db: Session = Depends(get_db), user: dict = Depends(_admin)) -> list[dict]:
    return svc.list_negotiated(db)


@router.post("/negotiated")
def upsert_negotiated(body: dict = Body(...), db: Session = Depends(get_db),
                      user: dict = Depends(_admin)) -> dict:
    return svc.upsert_negotiated(db, user, body.get("kind", "TARIFF"), body.get("code", ""),
                                 body.get("rate", 0.0))


@router.delete("/negotiated/{kind}/{code}")
def delete_negotiated(kind: str, code: str, db: Session = Depends(get_db),
                      user: dict = Depends(_admin)) -> dict:
    svc.delete_negotiated(db, user, kind, code)
    return {"ok": True}


# ── the practice register: who a billing practice is, and whether it may bill ──
@router.post("/practices")
def upsert_practice(body: dict = Body(...), db: Session = Depends(get_db),
                    user: dict = Depends(_admin)) -> dict:
    fields = {k: body[k] for k in practices.EDITABLE if k in body}     # nothing else is settable
    return practices.upsert(db, user, body.get("provider_id"), **fields)


@router.post("/practices/import")
def import_practices(body: dict = Body(...), db: Session = Depends(get_db),
                     user: dict = Depends(_admin)) -> dict:
    return practices.import_csv(db, user, body.get("csv", ""))


@router.post("/practices/{provider_id}/status")
def set_practice_status(provider_id: str, body: dict = Body(...), db: Session = Depends(get_db),
                        user: dict = Depends(_admin)) -> dict:
    return practices.set_status(db, user, provider_id, body.get("status", ""), body.get("reason", ""))


# ── rails parties: who may sign onto the provider channel, and for which providers ──
@router.get("/rails-parties")
def rails_parties(db: Session = Depends(get_db), user: dict = Depends(_admin)) -> list[dict]:
    return parties.list_parties(db)


@router.post("/rails-parties")
def register_rails_party(body: dict = Body(...), db: Session = Depends(get_db),
                         user: dict = Depends(_admin)) -> dict:
    return parties.register(db, user, body.get("party_id", ""), body.get("name", ""),
                            body.get("kind", "PROVIDER"), body.get("providers"), body.get("public_jwk"))


@router.post("/rails-parties/{party_id}/status")
def set_rails_party_status(party_id: str, body: dict = Body(...), db: Session = Depends(get_db),
                           user: dict = Depends(_admin)) -> dict:
    return parties.set_status(db, user, party_id, body.get("status", ""))


@router.post("/rails-parties/{party_id}/providers")
def set_rails_party_providers(party_id: str, body: dict = Body(...), db: Session = Depends(get_db),
                              user: dict = Depends(_admin)) -> dict:
    return parties.set_providers(db, user, party_id, body.get("providers"))


@router.post("/rails-parties/{party_id}/key")
def rotate_rails_party_key(party_id: str, body: dict = Body(...), db: Session = Depends(get_db),
                           user: dict = Depends(_admin)) -> dict:
    return parties.rotate_key(db, user, party_id, body.get("public_jwk"))


# ── coding rules (§3b) ──
@router.get("/code-rules")
def code_rules(db: Session = Depends(get_db), user: dict = Depends(_admin)) -> list[dict]:
    return svc.list_code_rules(db)


@router.post("/code-rules")
def upsert_code_rule(body: dict = Body(...), db: Session = Depends(get_db),
                     user: dict = Depends(_admin)) -> dict:
    return svc.upsert_code_rule(db, user, body.get("code", ""), body.get("rule", ""),
                                param=body.get("param", 0.0), basis=body.get("basis", ""))


@router.delete("/code-rules/{code}")
def delete_code_rule(code: str, db: Session = Depends(get_db), user: dict = Depends(_admin)) -> dict:
    svc.delete_code_rule(db, user, code)
    return {"ok": True}


# ── signal-mode overrides (§11) ──
@router.get("/signal-modes")
def signal_modes(db: Session = Depends(get_db), user: dict = Depends(_admin)) -> list[dict]:
    return svc.list_signal_modes(db)


@router.post("/signal-modes")
def set_signal_mode(body: dict = Body(...), db: Session = Depends(get_db),
                    user: dict = Depends(_admin)) -> dict:
    return svc.set_signal_mode(db, user, body.get("code", ""), body.get("mode", ""),
                               note=body.get("note", ""), effective_from=body.get("effective_from"))


@router.delete("/signal-modes/{code}")
def clear_signal_mode(code: str, db: Session = Depends(get_db), user: dict = Depends(_admin)) -> dict:
    svc.clear_signal_mode(db, user, code)
    return {"ok": True}


# ── audit log ──
@router.get("/audit")
def audit(limit: int = Query(100, ge=1, le=1000), db: Session = Depends(get_db),
          user: dict = Depends(_admin)) -> list[dict]:
    return svc.list_audit(db, limit=limit)


@router.get("/audit/search")
def audit_search(area: str = Query("", max_length=40), actor: str = Query("", max_length=80),
                 q: str = Query("", max_length=100), date_from: Optional[date] = None,
                 date_to: Optional[date] = None, limit: int = Query(50, ge=1, le=200),
                 offset: int = Query(0, ge=0), db: Session = Depends(get_db),
                 user: dict = Depends(_admin)) -> dict:
    """The audit log, filtered and paged: `{rows, total}`."""
    rows, total = svc.search_audit(db, area=area, actor=actor, q=q, date_from=date_from,
                                   date_to=date_to, limit=limit, offset=offset)
    return {"rows": rows, "total": total}


@router.get("/audit/facets")
def audit_facets(db: Session = Depends(get_db), user: dict = Depends(_admin)) -> dict:
    return svc.audit_facets(db)
