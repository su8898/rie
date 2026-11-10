"""Dated reference rates — versions, supersession and the change trail (ported from CIE).

Approved amounts are date-specific, so a payment-rule rate is an append-only VERSION: adding a
rate for a later effective date SUPERSEDES the prior open version (closes its effective_to the day
before) and the old amount stays on the books. The engine then prices every line at the rate in
force on its SERVICE date (`engine.rate_on`), so a late claim is paid at the tariff of its day and
a tariff increase never reprices history.

Three reference tiers carry versions, keyed (source, kind, code, discipline):

    RPL         TARIFF code x provider discipline   (the ACCEPTED tariff)
    NEGOTIATED  TARIFF or NAPPI code                (the ENFORCEABLE contract rate)
    SEP         NAPPI code                          (single exit price, before the dispensing fee)

A key WITH versions is priced from them. A key without any keeps its undated row in ref_rpl /
ref_negotiated / ref_nappi_sep (the loader's snapshot), which is in force on every date. The first
dated change to such a key materialises that row as the `baseline` version, so nothing is lost.
The undated tables are kept equal to the rate in force today on every change, so simple readers
(the reference browser, coding analytics) stay current.

Maintenance is forward-only (a new version must start after every existing one) and every change
writes ref_rate_log (old -> new, who, why) and the admin audit log.
"""
from __future__ import annotations

import csv
import io
import math
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

import engine

from . import models
from .admin_service import _audit

BASELINE_FROM = date(1900, 1, 1)          # effective_from of a materialised undated rate
SOURCES = {"RPL": ("TARIFF",), "NEGOTIATED": ("TARIFF", "NAPPI"), "SEP": ("NAPPI",)}
MAX_IMPORT_ROWS = 20_000
MAX_ERRORS_REPORTED = 50
ONE_DAY = timedelta(days=1)

Key = tuple[str, str, str, str]           # (source, kind, code, discipline)
V = models.RefRateVersion


class RateError(Exception):
    """A refused rate operation; `status` is the HTTP status the API answers with."""

    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status, self.detail = status, detail


# ── parsing / keys ───────────────────────────────────────────────────────────
def make_key(source, kind, code, discipline) -> Key:
    src = (source or "").strip().upper()
    if src not in SOURCES:
        raise RateError(422, f"unknown source {source!r} — use RPL, NEGOTIATED or SEP")
    kinds = SOURCES[src]
    k = (kind or "").strip().upper() or (kinds[0] if len(kinds) == 1 else "")
    if k not in kinds:
        raise RateError(422, f"kind must be {' or '.join(kinds)} for {src}")
    raw = (code or "").strip()
    if not raw or len(raw) > 32:
        raise RateError(422, "code is required (at most 32 characters)")
    disc = (discipline or "").strip()
    if src == "RPL":
        if not disc or len(disc) > 64:
            raise RateError(422, "discipline is required for an RPL tariff rate")
    else:
        disc = ""
    return src, k, engine.normalise_code(k, raw), disc


def _rate(v) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise RateError(422, "rate must be a number") from None
    if not math.isfinite(x) or x < 0 or x > 1_000_000_000:
        raise RateError(422, "rate must be between 0 and 1,000,000,000")
    return engine.money(x)


def _date(v, label: str) -> date:
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v).strip())
    except ValueError:
        raise RateError(422, f"{label} must be a date (YYYY-MM-DD)") from None


def _pct(v) -> float:
    try:
        p = float(v)
    except (TypeError, ValueError):
        raise RateError(422, "percentage must be a number") from None
    if not math.isfinite(p) or p == 0 or p <= -100 or p > 1000:
        raise RateError(422, "percentage must be non-zero, above -100 and at most 1000")
    return p


def _target(key: Key) -> str:
    src, kind, code, disc = key
    return f"{src}:{kind}:{code}" + (f":{disc}" if disc else "")


# ── the undated tables (the loader's snapshot; kept equal to today's rate) ───
def _base_row(db: Session, key: Key):
    src, kind, code, disc = key
    if src == "RPL":
        return db.get(models.RefRpl, (code, disc))
    if src == "SEP":
        return db.get(models.RefNappiSep, code)
    for r in db.scalars(select(models.RefNegotiated).where(models.RefNegotiated.kind == kind)):
        if engine.normalise_code(kind, r.code) == code:      # stored codes may carry leading zeros
            return r
    return None


def _base_rate(db: Session, key: Key) -> Optional[float]:
    row = _base_row(db, key)
    if row is None:
        return None
    return row.sep if key[0] == "SEP" else row.rate


def _set_base(db: Session, key: Key, rate: Optional[float]) -> None:
    src, kind, code, disc = key
    row = _base_row(db, key)
    if rate is None:
        if row is not None:
            db.delete(row)
    elif row is None:
        db.add(models.RefRpl(code=code, discipline=disc, rate=rate) if src == "RPL"
               else models.RefNappiSep(nappi_code=code, sep=rate) if src == "SEP"
               else models.RefNegotiated(kind=kind, code=code, rate=rate))
    elif src == "SEP":
        row.sep = rate
    else:
        row.rate = rate
    db.flush()


# ── versions ─────────────────────────────────────────────────────────────────
def _versions(db: Session, key: Key) -> list[V]:
    src, kind, code, disc = key
    return list(db.scalars(select(V).where(V.source == src, V.kind == kind, V.code == code,
                                           V.discipline == disc).order_by(V.effective_from)))


def _in_force(vs: list[V], on: date) -> Optional[V]:
    live = [v for v in vs if v.effective_from <= on and (v.effective_to is None or on <= v.effective_to)]
    return max(live, key=lambda v: v.effective_from) if live else None


def _sync_base(db: Session, key: Key, today: date) -> None:
    """Keep the undated table equal to the rate in force today (none in force after a retirement
    removes the row; a key whose only versions start in the future is left as it is)."""
    db.flush()
    vs = _versions(db, key)
    cur = _in_force(vs, today)
    if cur is not None:
        _set_base(db, key, cur.rate)
    elif any(v.effective_from <= today for v in vs):
        _set_base(db, key, None)


def _log(db: Session, user: dict, row: V, action: str, old_rate, new_rate, old_from, new_from,
         note: str) -> None:
    db.add(models.RefRateLog(rate_id=row.id, source=row.source, kind=row.kind, code=row.code,
                             discipline=row.discipline, action=action, old_rate=old_rate,
                             new_rate=new_rate, old_effective_from=old_from,
                             new_effective_from=new_from, changed_by=user["username"], note=note))
    _audit(db, user, f"rate.{action.lower()}", _target((row.source, row.kind, row.code, row.discipline)),
           {"old_rate": old_rate, "new_rate": new_rate,
            "effective_from": new_from.isoformat() if new_from else None, "note": note})


def _apply_version(db: Session, user: dict, key: Key, value: float, eff: date, note: str,
                   origin: str, today: date) -> tuple[V, str]:
    """Core supersession (no commit): close the in-force prior version and insert the new dated
    one. Forward-only — refuses a date on or before an existing version. -> (row, action)."""
    if eff <= BASELINE_FROM:
        raise RateError(422, f"effective-from date must be after {BASELINE_FROM.isoformat()}")
    src, kind, code, disc = key
    vs = _versions(db, key)
    if not vs:
        base = _base_rate(db, key)
        if base is not None:                                 # keep the undated rate as history
            baseline = V(source=src, kind=kind, code=code, discipline=disc, rate=base,
                         effective_from=BASELINE_FROM, origin="baseline",
                         note="undated rate in force before the first dated version")
            db.add(baseline)
            db.flush()
            vs = [baseline]
    clash = next((v for v in vs if v.effective_from >= eff), None)
    if clash is not None:
        if clash.effective_from == eff:
            raise RateError(409, f"{_target(key)} already has a rate starting {eff.isoformat()}")
        raise RateError(409, f"a newer version of {_target(key)} already starts "
                             f"{clash.effective_from.isoformat()} — use a later effective date")
    prev = _in_force(vs, eff)                                # the version this one supersedes
    action, old_rate, old_from = "CREATE", None, None
    if prev is not None:
        action, old_rate, old_from = "SUPERSEDE", prev.rate, prev.effective_from
        prev.effective_to = eff - ONE_DAY                    # close it the day before
    row = V(source=src, kind=kind, code=code, discipline=disc, rate=value, effective_from=eff,
            origin=origin, note=note, created_by=user["username"])
    db.add(row)
    db.flush()                                               # assign row.id for the log
    _log(db, user, row, action, old_rate, value, old_from, eff, note)
    _sync_base(db, key, today)
    return row, action


def _dict(v: V) -> dict:
    return {"id": v.id, "source": v.source, "kind": v.kind, "code": v.code,
            "discipline": v.discipline, "rate": v.rate,
            "effective_from": v.effective_from.isoformat(),
            "effective_to": v.effective_to.isoformat() if v.effective_to else None,
            "origin": v.origin, "note": v.note, "created_by": v.created_by}


# ── mutations (ADMIN; every change is logged) ────────────────────────────────
def add_or_supersede(db: Session, user: dict, source, kind, code, discipline, rate, effective_from,
                     note: str = "", origin: str = "manual", today: Optional[date] = None) -> dict:
    """Add a new dated version (CREATE, or SUPERSEDE the version in force on that date)."""
    key = make_key(source, kind, code, discipline)
    row, action = _apply_version(db, user, key, _rate(rate), _date(effective_from, "effective-from date"),
                                 (note or "").strip()[:500], origin, today or date.today())
    db.commit()
    return {**_dict(row), "action": action}


def increase(db: Session, user: dict, source, kind, code, discipline, pct, effective_from,
             today: Optional[date] = None) -> dict:
    """Supersede one rate with rate x (1 + pct/100), effective from a new date."""
    key = make_key(source, kind, code, discipline)
    p, eff = _pct(pct), _date(effective_from, "effective-from date")
    row, action = _increase_key(db, user, key, p, eff, f"{p:+g}% increase", today or date.today())
    db.commit()
    return {**_dict(row), "action": action}


def _increase_key(db: Session, user: dict, key: Key, p: float, eff: date, note: str,
                  today: date) -> tuple[V, str]:
    vs = _versions(db, key)
    cur = _in_force(vs, eff - ONE_DAY)
    old = cur.rate if cur is not None else (None if vs else _base_rate(db, key))
    if old is None:
        raise RateError(404, f"{_target(key)} has no rate in force before {eff.isoformat()} to increase")
    new = engine.money(engine.D(old) * (engine.D(1) + engine.D(p) / engine.D(100)))
    return _apply_version(db, user, key, new, eff, note, "manual", today)


def bulk_increase(db: Session, user: dict, source, pct, effective_from, q: str = "",
                  discipline: str = "", today: Optional[date] = None) -> dict:
    """Supersede EVERY current rate matching the filter with rate x (1 + pct/100) from a new date
    — one new dated version each; the old rates stay for earlier service dates. A key that already
    has a version on or after the date is skipped and reported."""
    src = (source or "").strip().upper()
    if src not in ("RPL", "NEGOTIATED"):
        raise RateError(422, "bulk increase applies to RPL or NEGOTIATED rates")
    p, eff = _pct(pct), _date(effective_from, "effective-from date")
    today = today or date.today()
    rows = [r for r in _current_rows(db, src, q, discipline, eff - ONE_DAY) if r["rate"] is not None]
    if not rows:
        raise RateError(422, "no rates match the filter")
    done, skipped = 0, []
    for r in rows:
        key = (r["source"], r["kind"], r["code"], r["discipline"])
        try:
            with db.begin_nested():                          # one refusal cannot poison the batch
                _increase_key(db, user, key, p, eff, f"{p:+g}% increase (bulk)", today)
            done += 1
        except RateError as e:
            skipped.append(f"{_target(key)}: {e.detail}")
    if not done:
        db.rollback()
        raise RateError(409, f"nothing increased — {skipped[0]}")
    db.commit()
    return {"increased": done, "skipped": len(skipped), "skipped_detail": skipped[:MAX_ERRORS_REPORTED]}


def adjust(db: Session, user: dict, rate_id: int, rate, note: str = "",
           today: Optional[date] = None) -> dict:
    """Correct the amount of an existing version in place (same dates) — for capture errors."""
    row = db.get(V, rate_id)
    if row is None:
        raise RateError(404, "rate version not found")
    value = _rate(rate)
    if value == row.rate:
        raise RateError(422, "the new rate is the same as the current value")
    old, row.rate = row.rate, value
    _log(db, user, row, "ADJUST", old, value, row.effective_from, row.effective_from,
         (note or "").strip()[:500])
    _sync_base(db, (row.source, row.kind, row.code, row.discipline), today or date.today())
    db.commit()
    return _dict(row)


def retire(db: Session, user: dict, rate_id: int, effective_to, note: str = "",
           today: Optional[date] = None) -> dict:
    """Close a version as of an end date with no replacement — the key has no rate in force from
    the next day (until a later version starts)."""
    row = db.get(V, rate_id)
    if row is None:
        raise RateError(404, "rate version not found")
    eto = _date(effective_to, "end date")
    if eto < row.effective_from:
        raise RateError(422, "end date cannot be before the version's effective-from date")
    key = (row.source, row.kind, row.code, row.discipline)
    later = [v for v in _versions(db, key) if v.effective_from > row.effective_from]
    if later and eto >= min(v.effective_from for v in later):
        raise RateError(422, "end date would overlap the next version")
    was = row.effective_to
    row.effective_to = eto
    _log(db, user, row, "RETIRE", row.rate, row.rate, row.effective_from, row.effective_from,
         (note or "").strip()[:500]
         or f"closed (was {'open' if was is None else was.isoformat()}) as of {eto.isoformat()}")
    _sync_base(db, key, today or date.today())
    db.commit()
    return _dict(row)


def import_csv(db: Session, user: dict, text: str, default_source: str = "RPL",
               today: Optional[date] = None) -> dict:
    """Bulk add/supersede from CSV: code, rate, effective_from [, discipline, kind, source, note].
    A row that exactly matches an existing (key, effective_from) is SKIPPED; a bad row is reported
    and does not abort the batch."""
    reader = csv.DictReader(io.StringIO(text or ""))
    fields = {(f or "").strip().lower() for f in (reader.fieldnames or [])}
    if not {"code", "rate", "effective_from"} <= fields:
        raise RateError(422, "CSV needs a header row with at least: code, rate, effective_from")
    today = today or date.today()
    res = {"added": 0, "superseded": 0, "skipped": 0, "errors": []}
    n_err = 0
    for i, raw in enumerate(reader, start=2):                # row 1 is the header
        if i - 1 > MAX_IMPORT_ROWS:
            raise RateError(422, f"too many rows — at most {MAX_IMPORT_ROWS:,} per import")
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
        try:
            key = make_key(row.get("source") or default_source, row.get("kind"), row.get("code"),
                           row.get("discipline"))
            value, eff = _rate(row.get("rate")), _date(row.get("effective_from", ""), "effective_from")
            if any(v.effective_from == eff for v in _versions(db, key)):
                res["skipped"] += 1
                continue
            with db.begin_nested():
                _, action = _apply_version(db, user, key, value, eff, row.get("note") or "import",
                                           "import", today)
            res["superseded" if action == "SUPERSEDE" else "added"] += 1
        except RateError as e:
            n_err += 1
            if len(res["errors"]) < MAX_ERRORS_REPORTED:
                res["errors"].append(f"row {i}: {e.detail}")
    db.commit()
    res["failed"] = n_err
    res["total"] = res["added"] + res["superseded"] + res["skipped"] + n_err
    return res


# ── reads ────────────────────────────────────────────────────────────────────
def _row(key: Key, vs: Optional[list[V]], base: Optional[float], on: date) -> dict:
    src, kind, code, disc = key
    out = {"source": src, "kind": kind, "code": code, "discipline": disc, "rate": base,
           "version_id": None, "effective_from": None, "effective_to": None,
           "versions": len(vs or ()), "dated": bool(vs)}
    if vs:
        cur = _in_force(vs, on)
        out["rate"] = cur.rate if cur else None
        if cur:
            out.update(version_id=cur.id, effective_from=cur.effective_from.isoformat(),
                       effective_to=cur.effective_to.isoformat() if cur.effective_to else None)
    return out


def _version_map(db: Session, src: str, codes=None) -> dict[Key, list[V]]:
    stmt = select(V).where(V.source == src).order_by(V.effective_from)
    if codes is not None:
        stmt = stmt.where(V.code.in_(set(codes)))
    out: dict[Key, list[V]] = {}
    for v in db.scalars(stmt):
        out.setdefault((v.source, v.kind, v.code, v.discipline), []).append(v)
    return out


def _current_rows(db: Session, src: str, q: str, discipline: str, on: date) -> list[dict]:
    """Every RPL / NEGOTIATED key (undated or dated) with the rate in force on `on`."""
    q, disc = (q or "").strip(), (discipline or "").strip()
    base: dict[Key, float] = {}
    if src == "RPL":
        for r in db.scalars(select(models.RefRpl)):
            base[("RPL", "TARIFF", r.code, r.discipline)] = r.rate
    else:
        for r in db.scalars(select(models.RefNegotiated)):
            base[("NEGOTIATED", r.kind, engine.normalise_code(r.kind, r.code), "")] = r.rate
    vmap = _version_map(db, src)

    def keep(key: Key) -> bool:
        prefix = engine.normalise_code(key[1], q) if q else ""
        return (not q or key[2].startswith(prefix) or key[2].startswith(q)) and (not disc or key[3] == disc)

    return [_row(k, vmap.get(k), base.get(k), on) for k in sorted(set(base) | set(vmap)) if keep(k)]


def _sep_rows(db: Session, q: str, on: date, limit: int, offset: int) -> tuple[list[dict], int]:
    """SEP is ~540k rows, so it pages in SQL over the undated table; dated versions overlay the
    page, and a NAPPI code that exists only as dated versions is listed first."""
    q = (q or "").strip()
    cond = models.RefNappiSep.nappi_code.like(f"{q}%") if q else None
    count = select(func.count()).select_from(models.RefNappiSep)
    page = select(models.RefNappiSep).order_by(models.RefNappiSep.nappi_code)
    if cond is not None:
        count, page = count.where(cond), page.where(cond)
    vmap = {k: vs for k, vs in _version_map(db, "SEP").items() if not q or k[2].startswith(q)}
    based = set(db.scalars(select(models.RefNappiSep.nappi_code)
                           .where(models.RefNappiSep.nappi_code.in_({k[2] for k in vmap})))) if vmap else set()
    only = [_row(k, vs, None, on) for k, vs in sorted(vmap.items()) if k[2] not in based]
    total = (db.scalar(count) or 0) + len(only)
    take = only[offset:offset + limit]
    rest = limit - len(take)
    if rest > 0:
        skip = max(0, offset - len(only))
        for r in db.scalars(page.offset(skip).limit(rest)):
            key = ("SEP", "NAPPI", r.nappi_code, "")
            take.append(_row(key, vmap.get(key), r.sep, on))
    return take, total


def list_current(db: Session, source, q: str = "", discipline: str = "", on=None,
                 limit: int = 50, offset: int = 0) -> dict:
    """The rate in force on `on` (default today) per key, undated and dated alike."""
    src = (source or "").strip().upper()
    if src not in SOURCES:
        raise RateError(422, f"unknown source {source!r} — use RPL, NEGOTIATED or SEP")
    day = _date(on, "on") if on else date.today()
    if src == "SEP":
        items, total = _sep_rows(db, q, day, limit, offset)
    else:
        rows = _current_rows(db, src, q, discipline, day)
        items, total = rows[offset:offset + limit], len(rows)
    return {"source": src, "on": day.isoformat(), "total": total, "items": items}


def versions(db: Session, source, kind, code, discipline) -> list[dict]:
    """Every version of one key, newest first; an undated key answers with its single row."""
    key = make_key(source, kind, code, discipline)
    vs = _versions(db, key)
    if vs:
        return [_dict(v) for v in reversed(vs)]
    base = _base_rate(db, key)
    if base is None:
        return []
    src, k, c, d = key
    return [{"id": None, "source": src, "kind": k, "code": c, "discipline": d, "rate": base,
             "effective_from": None, "effective_to": None, "origin": "undated", "note": "",
             "created_by": ""}]


def log(db: Session, limit: int = 100, source: str = "", code: str = "") -> list[dict]:
    stmt = select(models.RefRateLog)
    if source:
        stmt = stmt.where(models.RefRateLog.source == source.strip().upper())
    if code:
        stmt = stmt.where(models.RefRateLog.code.in_({code.strip(), engine.normalise_code("TARIFF", code.strip())}))
    return [{"id": r.id, "rate_id": r.rate_id, "source": r.source, "kind": r.kind, "code": r.code,
             "discipline": r.discipline, "action": r.action, "old_rate": r.old_rate,
             "new_rate": r.new_rate,
             "old_effective_from": r.old_effective_from.isoformat() if r.old_effective_from else None,
             "new_effective_from": r.new_effective_from.isoformat() if r.new_effective_from else None,
             "changed_by": r.changed_by, "note": r.note,
             "changed_at": r.changed_at.isoformat() if r.changed_at else None}
            for r in db.scalars(stmt.order_by(models.RefRateLog.id.desc()).limit(limit))]


def summary(db: Session) -> dict:
    by_source = {s: 0 for s in SOURCES}
    keys: set[Key] = set()
    n = 0
    for v in db.scalars(select(V)):
        n += 1
        by_source[v.source] = by_source.get(v.source, 0) + 1
        keys.add((v.source, v.kind, v.code, v.discipline))
    last = db.scalar(select(func.max(models.RefRateLog.changed_at)))
    return {"versions": n, "dated_keys": len(keys), "by_source": by_source,
            "changes": db.scalar(select(func.count()).select_from(models.RefRateLog)) or 0,
            "last_change": last.isoformat() if last else None}


def export_csv(db: Session, source, on=None) -> str:
    """The rates in force on `on` as CSV, in the import layout. RPL and NEGOTIATED export every
    key; SEP exports its dated keys only (the undated register is the NAPPI price file)."""
    src = (source or "").strip().upper()
    if src not in SOURCES:
        raise RateError(422, f"unknown source {source!r} — use RPL, NEGOTIATED or SEP")
    day = _date(on, "on") if on else date.today()
    if src == "SEP":
        rows = [_row(k, vs, None, day) for k, vs in sorted(_version_map(db, "SEP").items())]
    else:
        rows = _current_rows(db, src, "", "", day)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["source", "kind", "code", "discipline", "rate", "effective_from", "effective_to"])
    for r in rows:
        if r["rate"] is not None:
            w.writerow([r["source"], r["kind"], r["code"], r["discipline"], f"{r['rate']:.2f}",
                        r["effective_from"] or "", r["effective_to"] or ""])
    return buf.getvalue()


def overlay(db: Session, nappi_codes=None) -> dict:
    """Dated versions shaped for the engine's RefBook: each value a list of
    (effective_from, effective_to | None, rate). SEP is limited to `nappi_codes` when given."""
    out = {"RPL": {}, "NEGOTIATED": {}, "SEP": {}}
    for (src, kind, code, disc), vs in _version_map(db, "RPL").items():
        out["RPL"].setdefault(code, {})[disc] = [(v.effective_from, v.effective_to, v.rate) for v in vs]
    for (src, kind, code, disc), vs in _version_map(db, "NEGOTIATED").items():
        out["NEGOTIATED"][(kind, code)] = [(v.effective_from, v.effective_to, v.rate) for v in vs]
    if nappi_codes is None or nappi_codes:
        for (src, kind, code, disc), vs in _version_map(db, "SEP", nappi_codes).items():
            out["SEP"][code] = [(v.effective_from, v.effective_to, v.rate) for v in vs]
    return out
