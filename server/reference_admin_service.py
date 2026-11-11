"""Reference data an administrator maintains on screen, beyond rates and price lists:

- diagnosis codes (ICD-10): add, correct, withdraw from use, remove, and load an edition by file;
- flat-rate exclusions: the tariff codes that are not compared with a flat rate;
- the code crosswalk: a code billed under another tariff, paid at the rate of a code in the
  loaded price list once the match is signed off.

All three were loaded once by a script or written into the program. Every change here is written
to the admin audit log. Diagnosis codes are a lookup: changing one alters no claim already
decided. Exclusions and CONFIRMED crosswalk entries do change how a line is priced, from the next
claim assessed.
"""
from __future__ import annotations

import csv
import io
import re
from typing import Optional

from sqlalchemy import delete, func, insert, or_, select
from sqlalchemy.orm import Session

from . import models
from .admin_service import AdminError, _audit
from .clock import utcnow
from .crosswalk import CONFIRMED, CROSSWALK, NEEDS_SME, NO_RAF, PROPOSED, XW

I = models.RefIcd10
N = models.RefNonBench
C = models.RefCrosswalk

MAX_IMPORT_ROWS = 120_000
MAX_ERRORS_REPORTED = 50


def _norm(code: str) -> str:
    """Tariff-code normalisation: the same rule the engine prices under (strip leading zeros)."""
    return code.lstrip("0") or "0"


def _clean(v, cap: int, label: str) -> str:
    s = "" if v is None else str(v).strip()
    if len(s) > cap:
        raise AdminError(f"{label} is too long (at most {cap} characters)")
    return s


# ══ diagnosis codes ══════════════════════════════════════════════════════════
# A letter, two digits, then an optional subdivision: S72, S72.0, S72.00, M8000/0.
ICD_CODE = re.compile(r"^[A-Z][0-9]{2}[0-9A-Z./+*-]{0,6}$")
ICD_FIELDS = ("description", "code3_desc", "chapter_desc", "valid_primary", "valid_clinical")
_TRUE = {"1", "true", "yes", "y", "t"}
_FALSE = {"0", "false", "no", "n", "f"}


def _icd_code(v) -> str:
    code = str(v or "").strip().upper()
    if not code:
        raise AdminError("enter the diagnosis code")
    if not ICD_CODE.match(code):
        raise AdminError(f"'{code}' is not an ICD-10 code: a letter, two digits and an optional "
                         "subdivision, for example S72.00")
    return code


def _flag(v, label: str, default: bool) -> bool:
    if v is None or v == "":
        return default
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in _TRUE:
        return True
    if s in _FALSE:
        return False
    raise AdminError(f"{label} must be yes or no")


def _icd_dict(r: I) -> dict:
    return {"code": r.code, "description": r.description, "code3_desc": r.code3_desc,
            "chapter_desc": r.chapter_desc, "valid_primary": bool(r.valid_primary),
            "valid_clinical": bool(r.valid_clinical)}


def _icd_values(body: dict, existing: Optional[I] = None) -> dict:
    get = lambda k, d: body[k] if k in body and body[k] is not None else d  # noqa: E731
    vals = {
        "description": _clean(get("description", existing.description if existing else ""), 500,
                              "description"),
        "code3_desc": _clean(get("code3_desc", existing.code3_desc if existing else ""), 500,
                             "category"),
        "chapter_desc": _clean(get("chapter_desc", existing.chapter_desc if existing else ""), 500,
                               "chapter"),
        "valid_clinical": _flag(body.get("valid_clinical"), "valid for clinical use",
                                existing.valid_clinical if existing else True),
        "valid_primary": _flag(body.get("valid_primary"), "valid as a primary diagnosis",
                               existing.valid_primary if existing else True),
    }
    if not vals["description"]:
        raise AdminError("enter the description")
    if vals["valid_primary"] and not vals["valid_clinical"]:
        raise AdminError("a code that is valid as a primary diagnosis must be valid for clinical use")
    return vals


def icd10_search(db: Session, q: str = "", use: str = "", limit: int = 50, offset: int = 0) -> dict:
    """`use`: primary (may be a primary diagnosis), clinical (may be coded), heading (a category
    or chapter heading that may not be coded on a claim)."""
    def where(stmt):
        text = (q or "").strip()
        if text:
            stmt = stmt.where(or_(I.code.ilike(f"{text}%"), I.description.ilike(f"%{text}%")))
        if use == "primary":
            stmt = stmt.where(I.valid_primary.is_(True))
        elif use == "clinical":
            stmt = stmt.where(I.valid_clinical.is_(True))
        elif use == "heading":
            stmt = stmt.where(I.valid_clinical.is_(False))
        return stmt
    total = db.scalar(where(select(func.count()).select_from(I))) or 0
    rows = db.scalars(where(select(I)).order_by(I.code).limit(limit).offset(offset))
    return {"total": total, "rows": [_icd_dict(r) for r in rows]}


def icd10_summary(db: Session) -> dict:
    total = db.scalar(select(func.count()).select_from(I)) or 0
    primary = db.scalar(select(func.count()).select_from(I).where(I.valid_primary.is_(True))) or 0
    clinical = db.scalar(select(func.count()).select_from(I).where(I.valid_clinical.is_(True))) or 0
    ed = db.get(models.RefEdition, "icd10")
    return {"total": total, "valid_primary": primary, "valid_clinical": clinical,
            "headings": total - clinical,
            "edition": ed.version if ed else "", "edition_loaded_at": ed.synced_at if ed else None}


def icd10_upsert(db: Session, user: dict, body: dict) -> dict:
    code = _icd_code(body.get("code"))
    row = db.get(I, code)
    vals = _icd_values(body, row)
    if row is None:
        db.add(I(code=code, **vals))
        _audit(db, user, "icd10.add", code, {"description": vals["description"]})
    else:
        changed = {f: {"from": getattr(row, f), "to": vals[f]} for f in ICD_FIELDS
                   if getattr(row, f) != vals[f]}
        for f in changed:
            setattr(row, f, vals[f])
        if changed:
            _audit(db, user, "icd10.update", code, {"changed": changed})
    db.commit()
    return _icd_dict(db.get(I, code))


def icd10_remove(db: Session, user: dict, code: str) -> dict:
    code = str(code or "").strip().upper()
    row = db.get(I, code)
    if row is None:
        raise AdminError(f"no diagnosis code {code}")
    _audit(db, user, "icd10.remove", code, {"description": row.description})
    db.delete(row)
    db.commit()
    return {"removed": code}


def _stamp_edition(db: Session, kind: str, label: str) -> None:
    n = db.scalar(select(func.count()).select_from(I)) or 0
    ed = db.get(models.RefEdition, kind)
    if ed is None:
        ed = models.RefEdition(kind=kind)
        db.add(ed)
    ed.version, ed.n = label, n
    ed.synced_at = utcnow().strftime("%Y-%m-%d %H:%M:%S")


def icd10_import(db: Session, user: dict, text: str, edition: str = "") -> dict:
    """Load diagnosis codes from a CSV file: `code` and `description`, with any of code3_desc,
    chapter_desc, valid_primary, valid_clinical. A code already held is updated where the file
    differs; a code not in the file is left alone. A row that cannot be read is reported and the
    rest still load. `edition` names what was loaded and is shown with the reference editions."""
    reader = csv.DictReader(io.StringIO(text or ""))
    names = {(f or "").strip().lower() for f in (reader.fieldnames or [])}
    if not {"code", "description"} <= names:
        raise AdminError("the file needs a header row with code and description columns")
    edition = _clean(edition, 120, "edition")
    existing = {r.code: r for r in db.scalars(select(I))}
    new_rows: list[dict] = []
    seen: set[str] = set()
    errors: list[str] = []
    updated = unchanged = failed = 0
    for i, raw in enumerate(reader, start=2):
        if i - 1 > MAX_IMPORT_ROWS:
            raise AdminError(f"too many rows: at most {MAX_IMPORT_ROWS:,} per file")
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items() if k}
        if not any(row.values()):
            continue
        try:
            code = _icd_code(row.get("code"))
            if code in seen:
                raise AdminError(f"code {code} is in the file twice")
            cur = existing.get(code)
            vals = _icd_values({k: row[k] for k in ICD_FIELDS if row.get(k, "") != ""}, cur)
        except AdminError as e:
            failed += 1
            if len(errors) < MAX_ERRORS_REPORTED:
                errors.append(f"row {i}: {e}")
            continue
        seen.add(code)
        if cur is None:
            new_rows.append({"code": code, **vals})
        elif any(getattr(cur, f) != vals[f] for f in ICD_FIELDS):
            for f in ICD_FIELDS:
                setattr(cur, f, vals[f])
            updated += 1
        else:
            unchanged += 1
    for j in range(0, len(new_rows), 2000):
        db.execute(insert(I), new_rows[j:j + 2000])
    db.flush()
    if edition and (new_rows or updated or unchanged):
        _stamp_edition(db, "icd10", edition)
    res = {"added": len(new_rows), "updated": updated, "unchanged": unchanged, "failed": failed,
           "errors": errors, "edition": edition}
    _audit(db, user, "icd10.import", edition or "file",
           {k: res[k] for k in ("added", "updated", "unchanged", "failed", "edition")})
    db.commit()
    return res


# ══ flat-rate exclusions ═════════════════════════════════════════════════════
def _priced_codes(db: Session) -> dict[str, dict[str, float]]:
    """normalised tariff code -> {discipline: rate in force today}, from the accepted tariff."""
    out: dict[str, dict[str, float]] = {}
    for r in db.scalars(select(models.RefRpl)):
        out.setdefault(_norm(r.code), {})[r.discipline] = r.rate
    return out


def list_exclusions(db: Session) -> list[dict]:
    priced = _priced_codes(db)
    rows = sorted(db.scalars(select(N)), key=lambda r: (_norm(r.code).zfill(8), r.code))
    return [{"code": r.code, "reason": r.reason, "origin": r.origin, "created_by": r.created_by,
             "created_at": r.created_at.isoformat() if r.created_at else None,
             "has_rate": _norm(r.code) in priced} for r in rows]


def add_exclusion(db: Session, user: dict, code: str, reason: str) -> dict:
    code = _clean(code, 32, "code")
    reason = _clean(reason, 300, "reason")
    if not code:
        raise AdminError("enter the tariff code")
    if not reason:
        raise AdminError("say why the code is not priced at a flat rate")
    have = {_norm(c): c for c in db.scalars(select(N.code))}
    if _norm(code) in have:
        raise AdminError(f"code {have[_norm(code)]} is already excluded")
    db.add(N(code=code, reason=reason, origin="manual", created_by=user["username"],
             created_at=utcnow()))
    _audit(db, user, "non_bench.add", code, {"reason": reason})
    db.commit()
    return next(r for r in list_exclusions(db) if r["code"] == code)


def remove_exclusion(db: Session, user: dict, code: str, reason: str = "") -> dict:
    row = db.get(N, code)
    if row is None:
        raise AdminError(f"code {code} is not excluded")
    _audit(db, user, "non_bench.remove", code,
           {"reason": _clean(reason, 300, "reason"), "was": row.reason})
    db.delete(row)
    db.commit()
    return {"removed": code}


# ══ code crosswalk ═══════════════════════════════════════════════════════════
STATUSES = (CONFIRMED, PROPOSED, NEEDS_SME, NO_RAF)
NEEDS_TARGET = (CONFIRMED, PROPOSED)


def seed_crosswalk(db: Session) -> None:
    """Fill an untouched, empty crosswalk from the built-in list. An administrator who has emptied
    the table has made a change, which the audit log shows, and is not overruled."""
    if db.scalar(select(func.count()).select_from(C)):
        return
    if db.scalar(select(func.count()).select_from(models.AdminAudit)
                 .where(models.AdminAudit.action.like("crosswalk.%"))):
        return
    seen: set[str] = set()
    for e in CROSSWALK:
        if _norm(e.coida) in seen:
            continue
        seen.add(_norm(e.coida))
        db.add(C(code=_norm(e.coida), billed_as=e.coida, family=e.family,
                 description=e.corpus_desc, target_code=e.raf, status=e.status,
                 evidence=e.evidence, origin="seed",
                 confirmed_by="built-in list" if e.status == CONFIRMED else ""))


def crosswalk_entries(db: Session) -> list[XW]:
    """The stored crosswalk in the shape `apply_crosswalk` reads."""
    return [XW(r.code, r.family, r.description, r.target_code, r.status, r.evidence)
            for r in db.scalars(select(C))]


def _effect(row: C, priced: dict[str, dict[str, float]]) -> tuple[str, Optional[dict]]:
    """What the entry does to pricing today, and the rates it would pay at."""
    target = priced.get(_norm(row.target_code)) if row.target_code else None
    if row.status != CONFIRMED:
        return "NOT_SIGNED_OFF", target
    if row.code in priced:
        return "OWN_RATE", target            # the billed code has a rate of its own, which wins
    if target is None:
        return "TARGET_UNPRICED", None       # nothing to pay at
    return "IN_USE", target


def _xw_dict(row: C, priced: dict[str, dict[str, float]]) -> dict:
    effect, rates = _effect(row, priced)
    return {"code": row.code, "billed_as": row.billed_as or row.code, "family": row.family,
            "description": row.description, "target_code": row.target_code, "status": row.status,
            "evidence": row.evidence, "origin": row.origin, "updated_by": row.updated_by,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            "confirmed_by": row.confirmed_by,
            "confirmed_at": row.confirmed_at.isoformat() if row.confirmed_at else None,
            "effect": effect,
            "target_rates": [{"discipline": d, "rate": r} for d, r in sorted((rates or {}).items())],
            "own_rate": row.code in priced}


def list_crosswalk(db: Session) -> list[dict]:
    priced = _priced_codes(db)
    order = {s: i for i, s in enumerate(STATUSES)}
    rows = sorted(db.scalars(select(C)), key=lambda r: (order.get(r.status, 9), r.family, r.code.zfill(8)))
    return [_xw_dict(r, priced) for r in rows]


def _get_xw(db: Session, code: str) -> C:
    row = db.get(C, _norm(str(code or "").strip()))
    if row is None:
        raise AdminError(f"no crosswalk entry for code {code}")
    return row


def upsert_crosswalk(db: Session, user: dict, body: dict) -> dict:
    """Add an entry, or change what is recorded about one. A new entry is PROPOSED when it names a
    target and NEEDS_SME when it does not. Changing the target of a CONFIRMED entry returns it to
    PROPOSED: the sign-off was for the old match."""
    billed = _clean(body.get("code"), 32, "billed code")
    if not billed:
        raise AdminError("enter the code as it is billed")
    target = _clean(body.get("target_code"), 32, "target code") or None
    if target and _norm(target) == _norm(billed):
        raise AdminError("a code cannot be matched to itself")
    vals = {"family": _clean(body.get("family"), 80, "family"),
            "description": _clean(body.get("description"), 300, "description"),
            "evidence": _clean(body.get("evidence"), 1000, "evidence")}
    row = db.get(C, _norm(billed))
    now = utcnow()
    if row is None:
        row = C(code=_norm(billed), billed_as=billed, target_code=target,
                status=PROPOSED if target else NEEDS_SME, origin="manual",
                updated_by=user["username"], updated_at=now, **vals)
        db.add(row)
        _audit(db, user, "crosswalk.add", row.code, {"target_code": target, "status": row.status})
    else:
        changed = {f: {"from": getattr(row, f), "to": v} for f, v in vals.items()
                   if getattr(row, f) != v}
        if (row.target_code or None) != target:
            changed["target_code"] = {"from": row.target_code, "to": target}
            if row.status == CONFIRMED:
                changed["status"] = {"from": CONFIRMED, "to": PROPOSED if target else NEEDS_SME}
                row.status = PROPOSED if target else NEEDS_SME
                row.confirmed_by, row.confirmed_at = "", None
            elif row.status in NEEDS_TARGET and not target:
                changed["status"] = {"from": row.status, "to": NEEDS_SME}
                row.status = NEEDS_SME
            elif row.status == NEEDS_SME and target:
                changed["status"] = {"from": NEEDS_SME, "to": PROPOSED}
                row.status = PROPOSED
            row.target_code = target
        for f, v in vals.items():
            setattr(row, f, v)
        if changed:
            row.updated_by, row.updated_at = user["username"], now
            _audit(db, user, "crosswalk.update", row.code, {"changed": changed})
    db.commit()
    return _xw_dict(row, _priced_codes(db))


def set_crosswalk_status(db: Session, user: dict, code: str, status: str, reason: str) -> dict:
    """Move an entry between statuses. Confirming is the sign-off that lets the entry change what
    is paid, so it needs a target and a reason and records who gave it."""
    row = _get_xw(db, code)
    status = str(status or "").strip().upper()
    if status not in STATUSES:
        raise AdminError("status must be one of: " + ", ".join(STATUSES))
    reason = _clean(reason, 500, "reason")
    if status == row.status:
        raise AdminError("the entry already has that status")
    if status in NEEDS_TARGET and not row.target_code:
        raise AdminError("name the code it is paid at before proposing or signing off the match")
    if status == CONFIRMED and not reason:
        raise AdminError("say who signed off the match and on what basis")
    old = row.status
    row.status = status
    now = utcnow()
    row.updated_by, row.updated_at = user["username"], now
    if status == CONFIRMED:
        row.confirmed_by, row.confirmed_at = user["username"], now
    else:
        row.confirmed_by, row.confirmed_at = "", None
    if status not in NEEDS_TARGET:
        row.target_code = None
    if reason:
        row.evidence = (f"{row.evidence}\n" if row.evidence else "") + \
            f"{now.date().isoformat()} {status.replace('_', ' ').lower()}: {reason}"
        row.evidence = row.evidence[-1000:]
    _audit(db, user, "crosswalk.status", row.code, {"from": old, "to": status, "reason": reason})
    db.commit()
    return _xw_dict(row, _priced_codes(db))


def remove_crosswalk(db: Session, user: dict, code: str) -> dict:
    row = _get_xw(db, code)
    _audit(db, user, "crosswalk.remove", row.code,
           {"target_code": row.target_code, "status": row.status})
    db.execute(delete(C).where(C.code == row.code))
    db.commit()
    return {"removed": row.code}
