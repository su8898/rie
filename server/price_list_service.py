"""Price lists — whole tariff editions, created and maintained by an administrator.

A price list is one edition of a tariff held as a unit: its name, edition, where it was
published, its legal standing, the conversion factors it prints, and its entries. An entry is one
figure: a code, in a discipline, under one price column, with a description, units and a rand
value (either may be absent, because some lists print units only).

Lifecycle:

    DRAFT      entries and header are edited freely; entries are added one by one or by file
    PUBLISHED  the list is fixed. A correction is made by issuing a new edition from it (copy),
               so what was published stays on the books
    RETIRED    kept for the record, no longer current

The legal standing of a published list can change (a court sets a tariff aside, or restores it).
That is a data change made here with a stated reason, not a release.

Holding a list prices nothing. The engine reads its rates from the dated rate store
(rates_service); nothing in this module writes to it. Every change is written to the admin
audit log.
"""
from __future__ import annotations

import csv
import io
import math
from datetime import date
from typing import Optional

from sqlalchemy import delete, func, insert, or_, select
from sqlalchemy.orm import Session

from . import models
from .admin_service import _audit
from .clock import utcnow

L = models.RefPriceList
E = models.RefPriceListEntry
F = models.RefPriceListFactor

# the engine's own vocabulary for the standing of a price source; ENDOGENOUS is for medians the
# system computes itself and is never the standing of a published list
LEGAL_STATUSES = ("ENFORCEABLE", "ACCEPTED", "INTERDICTED")
STATES = ("DRAFT", "PUBLISHED", "RETIRED")
MAX_IMPORT_ROWS = 100_000
MAX_ERRORS_REPORTED = 50
DEFAULT_COLUMN = "standard"

HEADER_FIELDS = ("name", "edition", "source", "legal_status", "status_note", "effective_from",
                 "effective_to", "notes")
ENTRY_FIELDS = ("discipline", "code", "alt_code", "price_column", "description", "units",
                "units_suffix", "value_rand", "unit_of_issue", "source_page", "note")
EXPORT_COLUMNS = ("discipline", "code", "alt_code", "price_column", "description", "units",
                  "units_suffix", "value_rand", "unit_of_issue", "source_page", "note")
# other names a file may use for the same column
ALIASES = {"column": "price_column", "value": "value_rand", "rate": "value_rand",
           "rand": "value_rand", "suffix": "units_suffix", "page": "source_page",
           "tariff_page": "source_page", "flags": "note"}
LIMITS = {"discipline": 120, "code": 40, "alt_code": 40, "price_column": 80,
          "description": 4000, "units_suffix": 8, "unit_of_issue": 20, "source_page": 20,
          "note": 500}


class PriceListError(Exception):
    """A refused price list operation; `status` is the HTTP status the API answers with."""

    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status, self.detail = status, detail


# ── parsing ──────────────────────────────────────────────────────────────────
def _number(v, label: str) -> Optional[float]:
    """A plain non-negative number, or None when blank. Spaces between thousands are accepted
    and a single comma is read as the decimal mark (the South African convention). A value with
    both a comma and a point is refused, because it cannot be read without guessing."""
    if v is None or isinstance(v, bool):
        if v is None:
            return None
        raise PriceListError(422, f"{label} must be a number")
    if isinstance(v, (int, float)):
        n = float(v)
    else:
        s = str(v).strip().replace(" ", "").replace("\u00a0", "")
        if not s:
            return None
        if "," in s and "." in s:
            raise PriceListError(
                422, f"{label} '{v}' has both a comma and a point; write it without a "
                     "thousands separator")
        try:
            n = float(s.replace(",", "."))
        except ValueError:
            raise PriceListError(422, f"{label} '{v}' is not a number") from None
    if not math.isfinite(n) or n < 0:
        raise PriceListError(422, f"{label} must be zero or more")
    if n > 1_000_000_000:
        raise PriceListError(422, f"{label} is too large")
    return n


def _date(v, label: str) -> Optional[date]:
    if v is None or v == "":
        return None
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v).strip())
    except ValueError:
        raise PriceListError(422, f"{label} must be a date as YYYY-MM-DD") from None


def _text(v, field: str) -> str:
    s = "" if v is None else str(v).strip()
    if len(s) > LIMITS.get(field, 300):
        raise PriceListError(422, f"{field.replace('_', ' ')} is too long "
                                  f"(at most {LIMITS.get(field, 300)} characters)")
    return s


def _entry_values(raw: dict) -> dict:
    """Clean one entry's fields. Codes are kept exactly as given: a price list is a record of
    what was published, and normalising a code here would lose that."""
    out = {f: _text(raw.get(f), f) for f in ENTRY_FIELDS if f not in ("units", "value_rand")}
    out["price_column"] = out["price_column"] or DEFAULT_COLUMN
    out["units"] = _number(raw.get("units"), "units")
    out["value_rand"] = _number(raw.get("value_rand"), "rand value")
    if not (out["code"] or out["alt_code"] or out["description"]):
        raise PriceListError(422, "an entry needs a code or a description")
    return out


# ── reads ────────────────────────────────────────────────────────────────────
def _get(db: Session, list_id: int) -> L:
    pl = db.get(L, list_id)
    if pl is None:
        raise PriceListError(404, "no such price list")
    return pl


def _counts(db: Session, ids: list[int]) -> dict[int, dict]:
    out = {i: {"entries": 0, "with_value": 0, "units_only": 0, "codes": 0, "disciplines": 0}
           for i in ids}
    if not ids:
        return out
    rows = db.execute(
        select(E.list_id, func.count(E.id), func.count(E.value_rand),
               func.count(func.distinct(E.discipline)))
        .where(E.list_id.in_(ids)).group_by(E.list_id)).all()
    for lid, n, valued, disciplines in rows:
        out[lid].update(entries=n, with_value=valued, disciplines=disciplines)
    for lid, n in db.execute(
            select(E.list_id, func.count(E.id))
            .where(E.list_id.in_(ids), E.value_rand.is_(None), E.units.is_not(None))
            .group_by(E.list_id)).all():
        out[lid]["units_only"] = n
    distinct_codes = (select(E.list_id, E.discipline, E.code, E.alt_code)
                      .where(E.list_id.in_(ids)).distinct().subquery())
    for lid, n in db.execute(select(distinct_codes.c.list_id, func.count())
                             .group_by(distinct_codes.c.list_id)).all():
        out[lid]["codes"] = n
    return out


def _dict(pl: L, counts: Optional[dict] = None) -> dict:
    d = {"id": pl.id, "name": pl.name, "edition": pl.edition, "source": pl.source,
         "legal_status": pl.legal_status, "status_note": pl.status_note, "state": pl.state,
         "effective_from": pl.effective_from.isoformat() if pl.effective_from else None,
         "effective_to": pl.effective_to.isoformat() if pl.effective_to else None,
         "notes": pl.notes, "copied_from": pl.copied_from,
         "created_by": pl.created_by,
         "created_at": pl.created_at.isoformat() if pl.created_at else None,
         "published_by": pl.published_by,
         "published_at": pl.published_at.isoformat() if pl.published_at else None,
         "retired_by": pl.retired_by,
         "retired_at": pl.retired_at.isoformat() if pl.retired_at else None}
    if counts is not None:
        d["counts"] = counts
    return d


def list_lists(db: Session) -> list[dict]:
    lists = list(db.scalars(select(L).order_by(L.state, L.name)))
    counts = _counts(db, [pl.id for pl in lists])
    order = {s: i for i, s in enumerate(("PUBLISHED", "DRAFT", "RETIRED"))}
    return sorted((_dict(pl, counts[pl.id]) for pl in lists),
                  key=lambda d: (order.get(d["state"], 9), d["name"].lower()))


def get(db: Session, list_id: int) -> dict:
    pl = _get(db, list_id)
    d = _dict(pl, _counts(db, [pl.id])[pl.id])
    d["factors"] = [{"name": f.name, "value": f.value}
                    for f in db.scalars(select(F).where(F.list_id == pl.id).order_by(F.name))]
    d["disciplines"] = [
        {"discipline": disc, "entries": n, "with_value": valued, "with_units": united}
        for disc, n, valued, united in db.execute(
            select(E.discipline, func.count(E.id), func.count(E.value_rand), func.count(E.units))
            .where(E.list_id == pl.id).group_by(E.discipline).order_by(func.min(E.seq)))]
    d["columns"] = [c for c, in db.execute(
        select(E.price_column).where(E.list_id == pl.id).group_by(E.price_column)
        .order_by(func.min(E.seq)))]
    if pl.copied_from:
        src = db.get(L, pl.copied_from)
        d["copied_from_name"] = src.name if src else None
    return d


def _entry_dict(e: E) -> dict:
    return {"id": e.id, "seq": e.seq, "discipline": e.discipline, "code": e.code,
            "alt_code": e.alt_code, "price_column": e.price_column,
            "description": e.description, "units": e.units, "units_suffix": e.units_suffix,
            "value_rand": e.value_rand, "unit_of_issue": e.unit_of_issue,
            "source_page": e.source_page, "note": e.note}


def _entry_filter(stmt, list_id: int, q: str, discipline: str, column: str, priced: str):
    stmt = stmt.where(E.list_id == list_id)
    q = (q or "").strip()
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(E.code.ilike(f"{q}%"), E.alt_code.ilike(f"{q}%"),
                              E.description.ilike(like)))
    if discipline:
        stmt = stmt.where(E.discipline == discipline)
    if column:
        stmt = stmt.where(E.price_column == column)
    if priced == "value":
        stmt = stmt.where(E.value_rand.is_not(None))
    elif priced == "units_only":
        stmt = stmt.where(E.value_rand.is_(None), E.units.is_not(None))
    elif priced == "none":
        stmt = stmt.where(E.value_rand.is_(None), E.units.is_(None))
    return stmt


def entries(db: Session, list_id: int, q: str = "", discipline: str = "", column: str = "",
            priced: str = "", limit: int = 50, offset: int = 0) -> dict:
    _get(db, list_id)
    total = db.scalar(_entry_filter(select(func.count(E.id)), list_id, q, discipline, column,
                                    priced))
    rows = db.scalars(_entry_filter(select(E), list_id, q, discipline, column, priced)
                      .order_by(E.seq, E.id).limit(limit).offset(offset))
    return {"total": total or 0, "rows": [_entry_dict(e) for e in rows]}


def export_csv(db: Session, list_id: int) -> str:
    _get(db, list_id)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(EXPORT_COLUMNS)
    for e in db.scalars(select(E).where(E.list_id == list_id).order_by(E.seq, E.id)):
        d = _entry_dict(e)
        w.writerow(["" if d[c] is None else d[c] for c in EXPORT_COLUMNS])
    return buf.getvalue()


def history(db: Session, list_id: int, limit: int = 200) -> list[dict]:
    _get(db, list_id)
    A = models.AdminAudit
    rows = db.scalars(select(A).where(A.action.like("price_list.%"), A.target == str(list_id))
                      .order_by(A.id.desc()).limit(limit))
    return [{"id": a.id, "actor": a.actor, "action": a.action, "detail": a.detail,
             "at": a.at.isoformat() if a.at else None} for a in rows]


# ── header ───────────────────────────────────────────────────────────────────
def _header_values(body: dict, partial: bool) -> dict:
    out: dict = {}
    for f in HEADER_FIELDS:
        if partial and f not in body:
            continue
        v = body.get(f)
        if f in ("effective_from", "effective_to"):
            out[f] = _date(v, f.replace("_", " "))
        elif f == "legal_status":
            s = (v or "ACCEPTED").strip().upper() if isinstance(v, str) or v is None else v
            if s not in LEGAL_STATUSES:
                raise PriceListError(422, "legal standing must be one of: "
                                          + ", ".join(LEGAL_STATUSES))
            out[f] = s
        else:
            s = "" if v is None else str(v).strip()
            cap = 4000 if f == "notes" else 500 if f in ("source", "status_note") else 160
            if len(s) > cap:
                raise PriceListError(422, f"{f.replace('_', ' ')} is too long")
            out[f] = s
    if "name" in out and not out["name"]:
        raise PriceListError(422, "a price list needs a name")
    return out


def _check_dates(pl: L) -> None:
    if pl.effective_from and pl.effective_to and pl.effective_to < pl.effective_from:
        raise PriceListError(422, "the end date is before the start date")


def _name_free(db: Session, name: str, except_id: Optional[int] = None) -> None:
    hit = db.scalar(select(L).where(func.lower(L.name) == name.lower()))
    if hit is not None and hit.id != except_id:
        raise PriceListError(409, f"a price list named '{hit.name}' already exists")


def create(db: Session, user: dict, body: dict) -> dict:
    vals = _header_values(body, partial=False)
    _name_free(db, vals["name"])
    pl = L(**vals, state="DRAFT", created_by=user["username"], created_at=utcnow())
    _check_dates(pl)
    db.add(pl)
    db.flush()
    _audit(db, user, "price_list.create", pl.id,
           {"name": pl.name, "edition": pl.edition, "legal_status": pl.legal_status})
    db.commit()
    return get(db, pl.id)


def update(db: Session, user: dict, list_id: int, body: dict) -> dict:
    pl = _get(db, list_id)
    vals = _header_values(body, partial=True)
    if pl.state == "RETIRED":
        raise PriceListError(409, "a retired price list cannot be changed")
    if pl.state == "PUBLISHED":
        fixed = [f for f in vals if f != "notes" and vals[f] != getattr(pl, f)]
        if fixed:
            raise PriceListError(
                409, "a published price list is fixed: only its notes can be edited. "
                     "Issue a new edition to change it, or use the legal standing action")
    changed = {}
    for f, v in vals.items():
        old = getattr(pl, f)
        if v != old:
            changed[f] = {"from": old.isoformat() if isinstance(old, date) else old,
                          "to": v.isoformat() if isinstance(v, date) else v}
            setattr(pl, f, v)
    if "name" in changed:
        _name_free(db, pl.name, except_id=pl.id)
    _check_dates(pl)
    if changed:
        _audit(db, user, "price_list.update", pl.id, {"name": pl.name, "changed": changed})
    db.commit()
    return get(db, pl.id)


def set_legal_status(db: Session, user: dict, list_id: int, legal_status: str,
                     reason: str) -> dict:
    """Change the legal standing of a list. Allowed on a published list, because standing changes
    after publication; a reason is required and recorded."""
    pl = _get(db, list_id)
    status = (legal_status or "").strip().upper()
    if status not in LEGAL_STATUSES:
        raise PriceListError(422, "legal standing must be one of: " + ", ".join(LEGAL_STATUSES))
    reason = (reason or "").strip()
    if not reason:
        raise PriceListError(422, "say why the legal standing is changing")
    if len(reason) > 500:
        raise PriceListError(422, "the reason is too long")
    if pl.state == "RETIRED":
        raise PriceListError(409, "a retired price list cannot be changed")
    if status == pl.legal_status:
        raise PriceListError(409, f"the legal standing is already {status.lower()}")
    old = pl.legal_status
    pl.legal_status, pl.status_note = status, reason
    _audit(db, user, "price_list.legal_status", pl.id,
           {"name": pl.name, "from": old, "to": status, "reason": reason})
    db.commit()
    return get(db, pl.id)


def set_factors(db: Session, user: dict, list_id: int, factors: list[dict]) -> dict:
    pl = _draft(db, list_id)
    clean: dict[str, float] = {}
    for f in factors:
        name = _text(f.get("name"), "name")
        value = _number(f.get("value"), "factor value")
        if not name or value is None:
            raise PriceListError(422, "each conversion factor needs a name and a value")
        if name.lower() in {n.lower() for n in clean}:
            raise PriceListError(422, f"the factor '{name}' is listed twice")
        clean[name] = value
    old = {f.name: f.value for f in db.scalars(select(F).where(F.list_id == pl.id))}
    if clean != old:
        db.execute(delete(F).where(F.list_id == pl.id))
        db.add_all(F(list_id=pl.id, name=n, value=v) for n, v in clean.items())
        _audit(db, user, "price_list.factors", pl.id,
               {"name": pl.name, "from": old, "to": clean})
    db.commit()
    return get(db, pl.id)


# ── lifecycle ────────────────────────────────────────────────────────────────
def _draft(db: Session, list_id: int) -> L:
    pl = _get(db, list_id)
    if pl.state != "DRAFT":
        raise PriceListError(
            409, f"this price list is {pl.state.lower()} and its entries are fixed. "
                 "Issue a new edition from it to make changes")
    return pl


def publish(db: Session, user: dict, list_id: int) -> dict:
    pl = _draft(db, list_id)
    n = db.scalar(select(func.count(E.id)).where(E.list_id == pl.id)) or 0
    if n == 0:
        raise PriceListError(409, "an empty price list cannot be published")
    if pl.effective_from is None:
        raise PriceListError(409, "set the date the price list takes effect before publishing")
    if not pl.source:
        raise PriceListError(409, "say where the price list was published before publishing")
    pl.state, pl.published_by, pl.published_at = "PUBLISHED", user["username"], utcnow()
    _audit(db, user, "price_list.publish", pl.id,
           {"name": pl.name, "entries": n, "legal_status": pl.legal_status,
            "effective_from": pl.effective_from.isoformat()})
    db.commit()
    return get(db, pl.id)


def retire(db: Session, user: dict, list_id: int, effective_to=None, note: str = "") -> dict:
    pl = _get(db, list_id)
    if pl.state != "PUBLISHED":
        raise PriceListError(409, "only a published price list can be retired")
    end = _date(effective_to, "end date") or utcnow().date()
    if pl.effective_from and end < pl.effective_from:
        raise PriceListError(422, "the end date is before the start date")
    pl.state, pl.effective_to = "RETIRED", end
    pl.retired_by, pl.retired_at = user["username"], utcnow()
    _audit(db, user, "price_list.retire", pl.id,
           {"name": pl.name, "effective_to": end.isoformat(), "note": (note or "").strip()[:500]})
    db.commit()
    return get(db, pl.id)


def copy(db: Session, user: dict, list_id: int, name: str, edition: str = "") -> dict:
    """Issue a new edition: a draft with the same entries and factors, to be changed and published
    in its turn. The list it came from is left as it was."""
    src = _get(db, list_id)
    name = (name or "").strip()
    if not name:
        raise PriceListError(422, "the new edition needs a name")
    _name_free(db, name)
    new = L(name=name, edition=(edition or "").strip() or src.edition, source=src.source,
            legal_status=src.legal_status, status_note=src.status_note, notes=src.notes,
            state="DRAFT", copied_from=src.id, created_by=user["username"], created_at=utcnow())
    db.add(new)
    db.flush()
    db.add_all(F(list_id=new.id, name=f.name, value=f.value)
               for f in db.scalars(select(F).where(F.list_id == src.id)))
    rows = [{**{f: getattr(e, f) for f in ENTRY_FIELDS}, "list_id": new.id, "seq": e.seq}
            for e in db.scalars(select(E).where(E.list_id == src.id).order_by(E.seq, E.id))]
    _bulk(db, rows)
    _audit(db, user, "price_list.copy", new.id,
           {"name": new.name, "from_id": src.id, "from_name": src.name, "entries": len(rows)})
    db.commit()
    return get(db, new.id)


def remove(db: Session, user: dict, list_id: int) -> dict:
    pl = _get(db, list_id)
    if pl.state != "DRAFT":
        raise PriceListError(409, "only a draft can be deleted. Retire a published price list")
    n = db.scalar(select(func.count(E.id)).where(E.list_id == pl.id)) or 0
    db.execute(delete(E).where(E.list_id == pl.id))
    db.execute(delete(F).where(F.list_id == pl.id))
    _audit(db, user, "price_list.delete", pl.id, {"name": pl.name, "entries": n})
    db.delete(pl)
    db.commit()
    return {"deleted": list_id, "entries": n}


# ── entries ──────────────────────────────────────────────────────────────────
def _bulk(db: Session, rows: list[dict]) -> None:
    for i in range(0, len(rows), 2000):
        db.execute(insert(E), rows[i:i + 2000])


def _next_seq(db: Session, list_id: int) -> int:
    return (db.scalar(select(func.max(E.seq)).where(E.list_id == list_id)) or 0) + 1


def _label(e: E) -> dict:
    return {"discipline": e.discipline, "code": e.code or e.alt_code,
            "price_column": e.price_column}


def add_entry(db: Session, user: dict, list_id: int, body: dict) -> dict:
    pl = _draft(db, list_id)
    vals = _entry_values(body)
    e = E(list_id=pl.id, seq=_next_seq(db, pl.id), **vals)
    db.add(e)
    db.flush()
    _audit(db, user, "price_list.entry.add", pl.id,
           {"name": pl.name, **_label(e), "units": e.units, "value_rand": e.value_rand})
    db.commit()
    return _entry_dict(e)


def _entry(db: Session, list_id: int, entry_id: int) -> E:
    e = db.get(E, entry_id)
    if e is None or e.list_id != list_id:
        raise PriceListError(404, "no such entry in this price list")
    return e


def update_entry(db: Session, user: dict, list_id: int, entry_id: int, body: dict) -> dict:
    pl = _draft(db, list_id)
    e = _entry(db, list_id, entry_id)
    vals = _entry_values({**{f: getattr(e, f) for f in ENTRY_FIELDS}, **body})
    changed = {f: {"from": getattr(e, f), "to": v} for f, v in vals.items() if getattr(e, f) != v}
    for f in changed:
        setattr(e, f, vals[f])
    if changed:
        _audit(db, user, "price_list.entry.update", pl.id,
               {"name": pl.name, **_label(e), "changed": changed})
    db.commit()
    return _entry_dict(e)


def delete_entry(db: Session, user: dict, list_id: int, entry_id: int) -> dict:
    pl = _draft(db, list_id)
    e = _entry(db, list_id, entry_id)
    _audit(db, user, "price_list.entry.delete", pl.id,
           {"name": pl.name, **_label(e), "units": e.units, "value_rand": e.value_rand})
    db.delete(e)
    db.commit()
    return {"deleted": entry_id}


def import_csv(db: Session, user: dict, list_id: int, text: str, mode: str = "append") -> dict:
    """Load entries from a CSV file into a draft. The header row names the columns: `code` is
    required, with any of discipline, alt_code, price_column (or column), description, units,
    units_suffix, value_rand (or value, rate), unit_of_issue, source_page (or page), note.

    `append` adds to what is there; `replace` clears the draft's entries first. A row that
    cannot be read is reported and left out; the rest of the file still loads. Rows that repeat
    a code already in the list are loaded and counted, because lists do print a code twice."""
    pl = _draft(db, list_id)
    if mode not in ("append", "replace"):
        raise PriceListError(422, "mode must be append or replace")
    reader = csv.DictReader(io.StringIO(text or ""))
    names = [(f or "").strip().lower() for f in (reader.fieldnames or [])]
    names = [ALIASES.get(n, n) for n in names]
    if "code" not in names and "alt_code" not in names:
        raise PriceListError(422, "the file needs a header row with a code column")
    if not ({"units", "value_rand", "description"} & set(names)):
        raise PriceListError(
            422, "the file needs at least one of these columns: value_rand, units, description")
    unknown = [n for n in names if n and n not in ENTRY_FIELDS]
    removed = 0
    if mode == "replace":
        removed = db.scalar(select(func.count(E.id)).where(E.list_id == pl.id)) or 0
        db.execute(delete(E).where(E.list_id == pl.id))
        seq, seen = 1, set()
    else:
        seq = _next_seq(db, pl.id)
        seen = set(db.execute(select(E.discipline, E.code, E.alt_code, E.price_column)
                              .where(E.list_id == pl.id)).tuples())
    rows: list[dict] = []
    errors: list[str] = []
    failed = duplicates = 0
    for i, raw in enumerate(reader, start=2):               # row 1 is the header
        if i - 1 > MAX_IMPORT_ROWS:
            raise PriceListError(422, f"too many rows: at most {MAX_IMPORT_ROWS:,} per file")
        row = {ALIASES.get(k2, k2): v for k, v in raw.items()
               if k is not None and (k2 := k.strip().lower())}
        if not any((v or "").strip() for v in row.values()):
            continue                                        # a blank line
        try:
            vals = _entry_values(row)
        except PriceListError as e:
            failed += 1
            if len(errors) < MAX_ERRORS_REPORTED:
                errors.append(f"row {i}: {e.detail}")
            continue
        key = (vals["discipline"], vals["code"], vals["alt_code"], vals["price_column"])
        if key in seen:
            duplicates += 1
        seen.add(key)
        rows.append({**vals, "list_id": pl.id, "seq": seq})
        seq += 1
    _bulk(db, rows)
    res = {"added": len(rows), "removed": removed, "failed": failed, "duplicates": duplicates,
           "errors": errors, "ignored_columns": unknown, "mode": mode}
    _audit(db, user, "price_list.import", pl.id,
           {"name": pl.name, **{k: res[k] for k in ("added", "removed", "failed", "duplicates",
                                                     "mode")}})
    db.commit()
    return res
