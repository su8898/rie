"""ADMIN management surface (SPECIFICATION §6) — users, statutory config, reference tiers, and
signal-mode overrides.

Every mutation is written to the append-only admin_audit log (CUD logging, §9). Signal-mode
changes (§11) are reference-data edits — effective-dated and audit-logged, never a code deploy —
and they feed the engine live via reference_data.build_mode_overrides. Grounded (law-cited) signals
are always SCORED and cannot be overridden.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import delete, desc, func, or_, select
from sqlalchemy.orm import Session

from engine.coding import CODE_RULES, PCT_OF_TIME, TIME_BLOCK
from engine.models import normalise_code
from engine.reasons import MODE, R
from engine.vocab import Maturity

from . import models, precision_service
from .security import hash_password

VALID_MODES = {"SHADOW", "ADVISORY", "SCORED"}
VALID_ROLES = {"HANDLER", "MEDICAL_OFFICER", "INVESTIGATOR", "LEGAL", "ADMIN"}


class AdminError(Exception):
    """Bad admin request (400)."""


def _audit(db: Session, user: dict, action: str, target: str = "", detail: Optional[dict] = None) -> None:
    db.add(models.AdminAudit(actor=user["username"], action=action, target=str(target),
                             detail=detail or {}))


# ── users ─────────────────────────────────────────────────────────────────────
def _get_user(db: Session, username: str) -> "models.AppUser":
    u = db.scalar(select(models.AppUser).where(models.AppUser.username == username))
    if u is None:
        raise AdminError(f"no such user: {username}")
    return u


def list_users(db: Session) -> list[dict]:
    return [{"id": u.id, "username": u.username, "role": u.role, "active": u.active}
            for u in db.scalars(select(models.AppUser).order_by(models.AppUser.username))]


def create_user(db: Session, user: dict, username: str, role: str, password: str) -> dict:
    if role not in VALID_ROLES:
        raise AdminError(f"invalid role: {role}")
    if not username or not password:
        raise AdminError("username and password required")
    if db.scalar(select(models.AppUser).where(models.AppUser.username == username)):
        raise AdminError(f"user already exists: {username}")
    db.add(models.AppUser(username=username, role=role,
                          password_hash=hash_password(password), active=True))
    _audit(db, user, "user.create", username, {"role": role})
    db.commit()
    return {"username": username, "role": role, "active": True}


def _keep_an_admin(db: Session, u: "models.AppUser") -> None:
    """Refuse a change that would leave the Fund with no active administrator."""
    if u.role == "ADMIN" and u.active:
        others = db.scalar(select(func.count()).select_from(models.AppUser).where(
            models.AppUser.role == "ADMIN", models.AppUser.active.is_(True), models.AppUser.id != u.id))
        if not others:
            raise AdminError("this is the last active administrator — make another user an administrator first")


def set_role(db: Session, user: dict, username: str, role: str) -> dict:
    if role not in VALID_ROLES:
        raise AdminError(f"invalid role: {role}")
    u = _get_user(db, username)
    if role != "ADMIN":
        _keep_an_admin(db, u)
    u.role = role
    _audit(db, user, "user.set_role", username, {"role": role})
    db.commit()
    return {"username": username, "role": role, "active": u.active}


def set_active(db: Session, user: dict, username: str, active: bool) -> dict:
    u = _get_user(db, username)
    if u.username == user["username"] and not active:
        raise AdminError("cannot deactivate yourself")
    if not active:
        _keep_an_admin(db, u)
    u.active = bool(active)
    _audit(db, user, "user.set_active", username, {"active": bool(active)})
    db.commit()
    return {"username": username, "role": u.role, "active": u.active}


def reset_password(db: Session, user: dict, username: str, password: str) -> dict:
    if not password:
        raise AdminError("password required")
    u = _get_user(db, username)
    u.password_hash = hash_password(password)
    _audit(db, user, "user.reset_password", username, {})
    db.commit()
    return {"username": username, "reset": True}


# ── statutory caps (s17(4)(c)) ─────────────────────────────────────────────────
def list_caps(db: Session) -> list[dict]:
    return [{"effective_from": c.effective_from.isoformat(), "annual_cap": c.annual_cap}
            for c in db.scalars(select(models.RefCap).order_by(models.RefCap.effective_from))]


def upsert_cap(db: Session, user: dict, effective_from, annual_cap: float) -> dict:
    eff = date.fromisoformat(effective_from) if isinstance(effective_from, str) else effective_from
    c = db.get(models.RefCap, eff)
    if c:
        c.annual_cap = float(annual_cap)
    else:
        db.add(models.RefCap(effective_from=eff, annual_cap=float(annual_cap)))
    _audit(db, user, "cap.upsert", eff.isoformat(), {"annual_cap": float(annual_cap)})
    db.commit()
    return {"effective_from": eff.isoformat(), "annual_cap": float(annual_cap)}


def delete_cap(db: Session, user: dict, effective_from) -> None:
    eff = date.fromisoformat(effective_from) if isinstance(effective_from, str) else effective_from
    db.execute(delete(models.RefCap).where(models.RefCap.effective_from == eff))
    _audit(db, user, "cap.delete", eff.isoformat())
    db.commit()


# ── pre-auth code classes + negotiated rates (ruleset / ENFORCEABLE tier) ──────
def list_preauth(db: Session) -> list[str]:
    return [r.code for r in db.scalars(select(models.RefPreauth).order_by(models.RefPreauth.code))]


def add_preauth(db: Session, user: dict, code: str) -> None:
    if db.get(models.RefPreauth, code) is None:
        db.add(models.RefPreauth(code=code))
        _audit(db, user, "preauth.add", code)
        db.commit()


def remove_preauth(db: Session, user: dict, code: str) -> None:
    db.execute(delete(models.RefPreauth).where(models.RefPreauth.code == code))
    _audit(db, user, "preauth.remove", code)
    db.commit()


def list_negotiated(db: Session) -> list[dict]:
    return [{"kind": r.kind, "code": r.code, "rate": r.rate}
            for r in db.scalars(select(models.RefNegotiated)
                                .order_by(models.RefNegotiated.kind, models.RefNegotiated.code))]


def _refuse_if_dated(db: Session, kind: str, code: str) -> None:
    """A negotiated rate with dated versions is priced from them (rates_service); editing the
    undated row would change nothing and mislead, so it is refused here."""
    if db.scalar(select(models.RefRateVersion.id).where(
            models.RefRateVersion.source == "NEGOTIATED", models.RefRateVersion.kind == kind,
            models.RefRateVersion.code == normalise_code(kind, code)).limit(1)) is not None:
        raise AdminError(f"{kind}:{code} has dated versions — maintain it under Rates")


def upsert_negotiated(db: Session, user: dict, kind: str, code: str, rate: float) -> dict:
    _refuse_if_dated(db, kind, code)
    existing = db.scalar(select(models.RefNegotiated).where(
        models.RefNegotiated.kind == kind, models.RefNegotiated.code == code))
    if existing:
        existing.rate = float(rate)
    else:
        db.add(models.RefNegotiated(kind=kind, code=code, rate=float(rate)))
    _audit(db, user, "negotiated.upsert", f"{kind}:{code}", {"rate": float(rate)})
    db.commit()
    return {"kind": kind, "code": code, "rate": float(rate)}


def delete_negotiated(db: Session, user: dict, kind: str, code: str) -> None:
    _refuse_if_dated(db, kind, code)
    db.execute(delete(models.RefNegotiated).where(
        models.RefNegotiated.kind == kind, models.RefNegotiated.code == code))
    _audit(db, user, "negotiated.delete", f"{kind}:{code}")
    db.commit()


# ── signal-mode overrides (§11 promotion lifecycle) ────────────────────────────
# ── coding rules (§3b) — the tariff's own billing rules, as reference data ─────
def _code_rule_out(r: "models.RefCodeRule") -> dict:
    return {"code": r.code, "rule": r.rule, "param": r.param, "basis": r.basis, "origin": r.origin}


def list_code_rules(db: Session) -> list[dict]:
    return [_code_rule_out(r) for r in db.scalars(
        select(models.RefCodeRule).order_by(models.RefCodeRule.rule, models.RefCodeRule.code))]


def upsert_code_rule(db: Session, user: dict, code: str, rule: str, param=0.0, basis: str = "") -> dict:
    """One rule per tariff code. TIME_BLOCK needs its block length in minutes; PCT_OF_TIME needs
    its share (0–1]; the other rules take no parameter."""
    nc = normalise_code("TARIFF", str(code or "").strip())
    if not str(code or "").strip():
        raise AdminError("code is required")
    if rule not in CODE_RULES:
        raise AdminError(f"rule must be one of {sorted(CODE_RULES)}")
    try:
        param = float(param or 0.0)
    except (TypeError, ValueError):
        raise AdminError("param must be a number") from None
    if rule == TIME_BLOCK and not (0 < param <= 1440):
        raise AdminError("TIME_BLOCK needs param = block length in minutes (1–1440)")
    if rule == PCT_OF_TIME and not (0 < param <= 1):
        raise AdminError("PCT_OF_TIME needs param = share of anaesthetic time (0–1], e.g. 0.5")
    if rule not in (TIME_BLOCK, PCT_OF_TIME):
        param = 0.0
    row = db.get(models.RefCodeRule, nc)
    if row is None:
        row = models.RefCodeRule(code=nc, created_by=user["username"])
        db.add(row)
    row.rule, row.param, row.basis, row.origin = rule, param, str(basis or "")[:300], "manual"
    _audit(db, user, "code_rule.upsert", nc, {"rule": rule, "param": param})
    db.commit()
    return _code_rule_out(row)


def delete_code_rule(db: Session, user: dict, code: str) -> None:
    nc = normalise_code("TARIFF", str(code or "").strip())
    if db.get(models.RefCodeRule, nc) is None:
        raise AdminError(f"no coding rule on code {code}")
    db.execute(delete(models.RefCodeRule).where(models.RefCodeRule.code == nc))
    _audit(db, user, "code_rule.delete", nc)
    db.commit()


def list_signal_modes(db: Session) -> list[dict]:
    overrides = {r.code: r for r in db.scalars(select(models.RefSignalMode))}
    recs = {r["signal"]: r for r in precision_service.precision_by_signal(db)}
    out = []
    for code, meta in sorted(R.items()):
        default = MODE.get(code).name if code in MODE else "SCORED"
        ov, rec = overrides.get(code), recs.get(code, {})
        out.append({
            "signal": code, "maturity": meta.maturity.name, "category": meta.category.name,
            "default_mode": default, "effective_mode": ov.mode if ov else default,
            "overridden": ov is not None,
            "effective_from": ov.effective_from.isoformat() if ov else None,
            "set_by": ov.set_by if ov else None, "note": ov.note if ov else "",
            "overridable": meta.maturity is not Maturity.GROUNDED,
            "substantiation": rec.get("substantiation"), "wilson_lower": rec.get("wilson_lower"),
            "recommended_mode": rec.get("recommended_mode"),
        })
    return out


def set_signal_mode(db: Session, user: dict, code: str, mode: str, note: str = "",
                    effective_from=None) -> dict:
    meta = R.get(code)
    if meta is None:
        raise AdminError(f"unknown signal: {code}")
    if meta.maturity is Maturity.GROUNDED:
        raise AdminError(f"{code} is Grounded (law-cited) — always SCORED, not overridable")
    if mode not in VALID_MODES:
        raise AdminError(f"invalid mode: {mode} (SHADOW | ADVISORY | SCORED)")
    eff = (date.fromisoformat(effective_from) if isinstance(effective_from, str)
           else effective_from or date.today())
    existing = db.get(models.RefSignalMode, code)
    if existing:
        existing.mode, existing.effective_from = mode, eff
        existing.set_by, existing.note = user["username"], note
    else:
        db.add(models.RefSignalMode(code=code, mode=mode, effective_from=eff,
                                    set_by=user["username"], note=note))
    _audit(db, user, "signal_mode.set", code, {"mode": mode, "note": note})
    db.commit()
    return {"signal": code, "mode": mode, "effective_from": eff.isoformat()}


def clear_signal_mode(db: Session, user: dict, code: str) -> None:
    db.execute(delete(models.RefSignalMode).where(models.RefSignalMode.code == code))
    _audit(db, user, "signal_mode.clear", code)
    db.commit()


# ── audit log ─────────────────────────────────────────────────────────────────
def list_audit(db: Session, limit: int = 100) -> list[dict]:
    return [{"id": a.id, "actor": a.actor, "action": a.action, "target": a.target,
             "detail": a.detail, "at": a.at.isoformat() if a.at else None}
            for a in db.scalars(select(models.AdminAudit)
                                .order_by(desc(models.AdminAudit.id)).limit(limit))]


def _audit_out(a: "models.AdminAudit") -> dict:
    return {"id": a.id, "actor": a.actor, "action": a.action, "target": a.target,
            "detail": a.detail, "at": a.at.isoformat() if a.at else None}


def search_audit(db: Session, *, area: str = "", actor: str = "", q: str = "",
                 date_from=None, date_to=None, limit: int = 50, offset: int = 0) -> tuple[list[dict], int]:
    """The audit log, filtered and paged, newest first. `area` is the part of the action before
    the dot (user, cap, rate, …); `q` matches the action or the target."""
    stmt = select(models.AdminAudit)
    if area:
        stmt = stmt.where(models.AdminAudit.action.like(f"{area}.%"))
    if actor:
        stmt = stmt.where(models.AdminAudit.actor == actor)
    if q and q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(models.AdminAudit.target.ilike(like), models.AdminAudit.action.ilike(like)))
    if date_from:
        stmt = stmt.where(models.AdminAudit.at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        stmt = stmt.where(models.AdminAudit.at < datetime.combine(date_to, datetime.min.time()) + timedelta(days=1))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(desc(models.AdminAudit.id)).limit(limit).offset(offset))
    return [_audit_out(a) for a in rows], total


def audit_facets(db: Session) -> dict:
    """Who has made changes, and in which areas — for the audit log's filters."""
    actors = sorted(a for a in db.scalars(select(models.AdminAudit.actor).distinct()) if a)
    areas = sorted({a.split(".", 1)[0] for a in db.scalars(select(models.AdminAudit.action).distinct()) if a})
    return {"actors": actors, "areas": areas}
