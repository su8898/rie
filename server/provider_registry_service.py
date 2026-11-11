"""The practice register — who a billing practice is, and whether it may bill the Fund.

Ported from CIE's provider identity registry: a local, administrator-maintained stand-in for the
BHF practice-number register until a live feed is granted. `provider_id` IS the practice number.

At claim intake the register decides three fund-side facts a submitter must not be trusted to
assert for itself (`apply`):

  registration  a practice the register marks SUSPENDED or DEREGISTERED may not bill, so the
                claim is PROVIDER_UNREGISTERED and payment is blocked. With enforcement on
                (RIE_PROVIDER_REGISTER_ENFORCED=1) a practice that is not in the register at all
                is refused the same way.
  discipline    a verified row's discipline is the one a line is priced under, whatever the
                submitter put on the line. The asserted value is kept beside it.
  setting       a claim whose practices are all registered as a hospital or emergency unit is a
                facility account; one whose practices are all registered rooms-based is not.

A practice the register does not know leaves the claim as submitted (unless enforcement is on).
"""
from __future__ import annotations

import csv
import io
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from . import config, models
from .admin_service import AdminError, _audit

PRACTICE_TYPES = {"", "INDIVIDUAL", "GROUP", "INSTITUTION", "SUPPLIER"}
SETTINGS = {"", "ROOMS", "HOSPITAL", "ER", "MIXED"}
STATUSES = {"ACTIVE", "SUSPENDED", "DEREGISTERED"}
FACILITY_SETTINGS = {"HOSPITAL", "ER"}
_TEXT = ("practice_name", "discipline", "professional_nr", "notes")
EDITABLE = (*_TEXT, "practice_type", "setting", "verified")     # what a caller may set on a row
MAX_IMPORT = 20_000


def _out(r: "models.ProviderRegistry") -> dict:
    return {"provider_id": r.provider_id, "practice_name": r.practice_name, "discipline": r.discipline,
            "practice_type": r.practice_type, "setting": r.setting, "professional_nr": r.professional_nr,
            "status": r.status, "status_reason": r.status_reason, "source": r.source,
            "verified": r.verified, "notes": r.notes, "updated_by": r.updated_by,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None}


# ── identity ─────────────────────────────────────────────────────────────────
def resolve_identity(db: Session, provider_id: str) -> dict:
    """What the Fund knows about a practice number: its register row, or that it is unknown."""
    row = db.get(models.ProviderRegistry, provider_id)
    if row is None:
        return {"provider_id": provider_id, "known": False, "may_bill": not config.PROVIDER_REGISTER_ENFORCED}
    return {**_out(row), "known": True, "may_bill": row.status == "ACTIVE"}


# ── intake ───────────────────────────────────────────────────────────────────
def apply(db: Session, payload: dict) -> dict:
    """Return the claim payload with its fund-side provider facts taken from the register."""
    lines = payload.get("lines") or []
    ids = {l["provider_id"] for l in lines}
    if not ids:
        return payload
    rows = {r.provider_id: r for r in db.scalars(
        select(models.ProviderRegistry).where(models.ProviderRegistry.provider_id.in_(ids)))}
    barred = sorted(p for p in ids if (p in rows and rows[p].status != "ACTIVE")
                    or (p not in rows and config.PROVIDER_REGISTER_ENFORCED))
    out = dict(payload)
    if barred:
        out["provider_registered"] = False
        out["provider_register_barred"] = barred                # which practice, for the reviewer
    new_lines = []
    for l in lines:
        row = rows.get(l["provider_id"])
        if row is not None and row.verified and row.discipline and l.get("discipline") != row.discipline:
            asserted = str(l.get("discipline") or "")
            l = {**l, "discipline": row.discipline}
            if asserted:                                        # keep what the submitter claimed
                l["discipline_asserted"] = asserted
        new_lines.append(l)
    out["lines"] = new_lines
    settings = {rows[p].setting for p in ids if p in rows and rows[p].setting}
    if len(rows) == len(ids) and settings:                      # every practice on the claim is known
        if settings <= FACILITY_SETTINGS:
            out["facility"] = True
        elif settings == {"ROOMS"}:
            out["facility"] = False
    return out


# ── maintenance (ADMIN; every change audit-logged) ───────────────────────────
def _clean(fields: dict) -> dict:
    out = {k: str(fields.get(k) or "").strip()[:300] for k in _TEXT if k in fields}
    for key, allowed, label in (("practice_type", PRACTICE_TYPES, "practice type"), ("setting", SETTINGS, "setting")):
        if key in fields:
            value = str(fields.get(key) or "").strip().upper()
            if value not in allowed:
                raise AdminError(f"{label} must be one of {', '.join(sorted(x for x in allowed if x))}")
            out[key] = value
    if "verified" in fields:
        out["verified"] = bool(fields["verified"])
    return out


def _id(provider_id) -> str:
    pid = str(provider_id or "").strip()
    if not pid or len(pid) > 64:
        raise AdminError("practice number is required (at most 64 characters)")
    return pid


def upsert(db: Session, user: dict, provider_id, source: str = "MANUAL", commit: bool = True, **fields) -> dict:
    """Add a practice, or change what is recorded about it. Status is changed by `set_status`."""
    pid = _id(provider_id)
    clean = _clean(fields)
    row = db.get(models.ProviderRegistry, pid)
    created = row is None
    if created:
        row = models.ProviderRegistry(provider_id=pid, status="ACTIVE")
        db.add(row)
    # an update records only what actually changed; an unchanged row is left alone (no audit noise)
    changed = clean if created else {k: v for k, v in clean.items() if getattr(row, k) != v}
    if created or changed:
        for k, v in changed.items():
            setattr(row, k, v)
        row.source, row.updated_by = source, user["username"]
        _audit(db, user, "provider_register.add" if created else "provider_register.update", pid, changed)
    if commit:
        db.commit()
    return _out(row)


def set_status(db: Session, user: dict, provider_id, status: str, reason: str = "") -> dict:
    """Suspend, deregister or reinstate a practice. A reason is required to bar one."""
    row = db.get(models.ProviderRegistry, _id(provider_id))
    if row is None:
        raise AdminError(f"practice {provider_id} is not in the register")
    if status not in STATUSES:
        raise AdminError(f"status must be one of {', '.join(sorted(STATUSES))}")
    reason = str(reason or "").strip()[:300]
    if status != "ACTIVE" and not reason:
        raise AdminError("a reason is required to suspend or deregister a practice")
    old, row.status, row.status_reason, row.updated_by = row.status, status, reason, user["username"]
    _audit(db, user, "provider_register.status", row.provider_id, {"from": old, "to": status, "reason": reason})
    db.commit()
    return _out(row)


SORTS = {"number": models.ProviderRegistry.provider_id, "name": models.ProviderRegistry.practice_name,
         "discipline": models.ProviderRegistry.discipline, "updated": models.ProviderRegistry.updated_at}


def list_practices(db: Session, q: str = "", status: str = "", page: int = 1, page_size: int = 25,
                   discipline: str = "", setting: str = "", practice_type: str = "",
                   verified: Optional[bool] = None, sort: str = "number", direction: str = "asc") -> dict:
    stmt = select(models.ProviderRegistry)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(models.ProviderRegistry.provider_id.ilike(like),
                              models.ProviderRegistry.practice_name.ilike(like),
                              models.ProviderRegistry.discipline.ilike(like),
                              models.ProviderRegistry.professional_nr.ilike(like)))
    if status:
        stmt = stmt.where(models.ProviderRegistry.status == status)
    if discipline:
        stmt = stmt.where(models.ProviderRegistry.discipline == discipline)
    if setting:
        stmt = stmt.where(models.ProviderRegistry.setting == setting)
    if practice_type:
        stmt = stmt.where(models.ProviderRegistry.practice_type == practice_type)
    if verified is not None:
        stmt = stmt.where(models.ProviderRegistry.verified.is_(verified))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    col = SORTS.get(sort, models.ProviderRegistry.provider_id)
    order = col.desc() if direction == "desc" else col.asc()
    rows = db.scalars(stmt.order_by(order, models.ProviderRegistry.provider_id)
                      .limit(page_size).offset((max(page, 1) - 1) * page_size))
    return {"total": total, "page": max(page, 1), "page_size": page_size, "items": [_out(r) for r in rows]}


def _unregistered_stmt(q: str = ""):
    """Practice numbers that have billed the Fund but have no register row."""
    line = models.BillingLineRecord
    stmt = (select(line.provider_id, func.count(func.distinct(line.claim_id)).label("n_claims"),
                   func.sum(line.billed).label("billed"), func.max(line.service_date).label("last_service"))
            .where(line.provider_id != "",
                   line.provider_id.not_in(select(models.ProviderRegistry.provider_id)))
            .group_by(line.provider_id))
    if q and q.strip():
        stmt = stmt.where(line.provider_id.ilike(f"%{q.strip()}%"))
    return stmt


def unregistered(db: Session, q: str = "", page: int = 1, page_size: int = 25) -> dict:
    """Who is billing without being in the register, the largest biller first."""
    stmt = _unregistered_stmt(q)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.execute(stmt.order_by(func.sum(models.BillingLineRecord.billed).desc(),
                                    models.BillingLineRecord.provider_id)
                      .limit(page_size).offset((max(page, 1) - 1) * page_size))
    return {"total": total, "page": max(page, 1), "page_size": page_size,
            "items": [{"provider_id": pid, "n_claims": n, "billed": round(billed or 0.0, 2),
                       "last_service": last.isoformat() if last else None} for pid, n, billed, last in rows]}


def summary(db: Session) -> dict:
    by_status = dict(db.execute(select(models.ProviderRegistry.status, func.count())
                                .group_by(models.ProviderRegistry.status)).all())
    return {"total": sum(by_status.values()), "by_status": by_status,
            "unregistered": db.scalar(select(func.count()).select_from(_unregistered_stmt().subquery())) or 0,
            "enforced": config.PROVIDER_REGISTER_ENFORCED}


def disciplines(db: Session) -> list[str]:
    """The disciplines in use in the register (for the filter)."""
    return sorted(d for d in db.scalars(select(models.ProviderRegistry.discipline).distinct()) if d)


def activity(db: Session, provider_id: str) -> dict:
    """What a practice has done with the Fund: what it billed and was paid, who may sign for it
    on the provider channel, and every change made to its register entry."""
    line = models.BillingLineRecord
    n_claims, n_lines, billed, payable, first, last = db.execute(
        select(func.count(func.distinct(line.claim_id)), func.count(), func.sum(line.billed),
               func.sum(line.payable), func.min(line.service_date), func.max(line.service_date))
        .where(line.provider_id == provider_id)).one()
    n_advices, paid, reduced = db.execute(
        select(func.count(), func.sum(models.Remittance.total_paid), func.sum(models.Remittance.total_reduced))
        .where(models.Remittance.provider_id == provider_id)).one()
    parties = [{"party_id": p.party_id, "name": p.name, "kind": p.kind, "status": p.status,
                "all_providers": "*" in (p.providers or [])}
               for p in db.scalars(select(models.RailsParty).order_by(models.RailsParty.party_id))
               if provider_id in (p.providers or []) or "*" in (p.providers or [])]
    history = [{"action": a.action.removeprefix("provider_register."), "actor": a.actor,
                "at": a.at.isoformat() if a.at else None, "detail": a.detail or {}}
               for a in db.scalars(select(models.AdminAudit)
                                   .where(models.AdminAudit.target == provider_id,
                                          models.AdminAudit.action.like("provider_register.%"))
                                   .order_by(models.AdminAudit.id.desc()).limit(200))]
    return {"provider_id": provider_id,
            "billing": {"n_claims": n_claims or 0, "n_lines": n_lines or 0, "billed": round(billed or 0.0, 2),
                        "payable": round(payable or 0.0, 2),
                        "first_service": first.isoformat() if first else None,
                        "last_service": last.isoformat() if last else None},
            "payments": {"n_advices": n_advices or 0, "paid": round(paid or 0.0, 2),
                         "reduced": round(reduced or 0.0, 2)},
            "parties": parties, "history": history}


def import_csv(db: Session, user: dict, text: str) -> dict:
    """Load practices from CSV: `provider_id` plus any of practice_name, discipline, practice_type,
    setting, professional_nr, notes. A row never changes a practice's status. Bad rows are
    reported and skipped; the good ones are loaded."""
    reader = csv.DictReader(io.StringIO(text or ""))
    if not reader.fieldnames or "provider_id" not in [f.strip() for f in reader.fieldnames]:
        raise AdminError("the CSV needs a provider_id column")
    loaded, errors = 0, []
    for n, raw in enumerate(reader, start=2):
        if n - 1 > MAX_IMPORT:
            raise AdminError(f"at most {MAX_IMPORT} rows per import")
        row = {(k or "").strip(): (v or "").strip() for k, v in raw.items()}
        try:
            upsert(db, user, row.get("provider_id"), source="IMPORT", commit=False,
                   **{k: row[k] for k in EDITABLE if k in row and k != "verified"})
            loaded += 1
        except AdminError as e:
            errors.append({"line": n, "error": str(e)})
    db.commit()
    return {"loaded": loaded, "errors": errors}


# ── the seam for a live register ─────────────────────────────────────────────
class RegisterFeed:
    """Where a live BHF practice-number feed plugs in. Not available: the Fund has no access yet.
    When it is granted, implement `lookup` and set AVAILABLE; `sync` then keeps rows current."""
    AVAILABLE = False

    def lookup(self, practice_number: str) -> Optional[dict]:      # pragma: no cover — no feed yet
        raise NotImplementedError("no live practice-number feed is connected")


def sync(db: Session, user: dict, provider_id: str, feed: Optional[RegisterFeed] = None) -> Optional[dict]:
    """Refresh one practice from the live feed. Returns None while no feed is available."""
    feed = feed or RegisterFeed()
    if not feed.AVAILABLE:
        return None
    data = feed.lookup(provider_id)
    if not data:
        return None
    return upsert(db, user, provider_id, source="PCNS", **data)
