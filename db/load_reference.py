"""Load the RAF reference data (reference.db) into RIE's reference tables.

reference.db (a SQLite snapshot) holds:
  ref_tariffs  — 1,367 gazetted 2026 tariff rates by provider discipline
  ref_nappi    — ~543k medicine/material unit prices (SEP source)
  ref_icd10    — ~41k diagnoses
  ref_meta     — edition provenance

Mapping into RIE:
  ref_tariffs -> ref_rpl        the operative ACCEPTED tariff reference (pay min(billed, rate)).
                                One (code, discipline) -> rate row per schedule entry — no
                                collapse; the engine resolves by the billing provider's discipline
                                (exact -> GP -> cheapest). The GP schedule is stored as "GP".
                                (To treat the tariff as INTERDICTED comparison-only instead, load
                                 into ref_raf2022 — a one-line change; the legal_status design
                                 supports the flip with no engine change.)
  ref_nappi   -> ref_nappi_sep  unit_price as SEP (NAPPI+dispensing-fee is ENFORCEABLE).
  ref_icd10   -> ref_icd10      diagnoses (validation/display).
  ref_meta    -> ref_edition    provenance stamped on the load.

This also creates the tables and seeds users + statutory config, so it is a self-contained
deploy-init:  python3 db/load_reference.py   (target DB = RIE_DATABASE_URL).
"""
from __future__ import annotations

import os
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import delete, insert  # noqa: E402

from server import models  # noqa: E402
from server.db import Base, SessionLocal, engine  # noqa: E402
from server.reference_data import _norm  # noqa: E402
from server.seed import seed  # noqa: E402

GP_DISCIPLINE = "Doctors and General Practitioners"
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REFERENCE_DB = os.environ.get("RIE_REFERENCE_DB", os.path.join(_ROOT, "reference.db"))
_CHUNK = 10_000


def _bulk(db, model, rows: list[dict]) -> None:
    for i in range(0, len(rows), _CHUNK):
        db.execute(insert(model), rows[i:i + _CHUNK])


def _load_tariffs(db, src) -> int:
    # One row per (normalised code, discipline) — no collapse; the engine resolves by discipline.
    # The GP schedule ("Doctors and General Practitioners") is stored as the canonical "GP" so the
    # resolver's GP fallback works.
    rows: dict = {}
    for r in src.execute("SELECT norm_code, discipline, rate FROM ref_tariffs "
                         "WHERE rate IS NOT NULL AND norm_code IS NOT NULL"):
        disc = "GP" if r["discipline"] == GP_DISCIPLINE else (r["discipline"] or "GP")
        rows[(_norm(r["norm_code"]), disc)] = float(r["rate"])
    db.execute(delete(models.RefRpl))
    _bulk(db, models.RefRpl, [{"code": c, "discipline": d, "rate": rate}
                              for (c, d), rate in rows.items()])
    return len(rows)


def _load_nappi(db, src) -> int:
    seen: dict = {}
    for r in src.execute("SELECT nappi_code, unit_price FROM ref_nappi "
                         "WHERE unit_price IS NOT NULL AND unit_price > 0 AND nappi_code IS NOT NULL"):
        code, price = r["nappi_code"], float(r["unit_price"])
        if code not in seen or price < seen[code]:          # conservative: keep the lowest SEP
            seen[code] = price
    db.execute(delete(models.RefNappiSep))
    _bulk(db, models.RefNappiSep, [{"nappi_code": c, "sep": p} for c, p in seen.items()])
    return len(seen)


def _load_icd10(db, src) -> int:
    icd: dict = {}
    for r in src.execute("SELECT code, description, code3_desc, chapter_desc, "
                         "valid_primary, valid_clinical FROM ref_icd10 WHERE code IS NOT NULL"):
        icd[r["code"]] = {"code": r["code"], "description": r["description"] or "",
                          "code3_desc": r["code3_desc"] or "", "chapter_desc": r["chapter_desc"] or "",
                          "valid_primary": bool(r["valid_primary"]),
                          "valid_clinical": bool(r["valid_clinical"])}
    db.execute(delete(models.RefIcd10))
    _bulk(db, models.RefIcd10, list(icd.values()))
    return len(icd)


def _load_editions(db, src) -> None:
    db.execute(delete(models.RefEdition))
    rows = [{"kind": r["kind"], "version": r["version"], "n": r["n"], "synced_at": r["synced_at"]}
            for r in src.execute("SELECT kind, version, n, synced_at FROM ref_meta")]
    if rows:
        _bulk(db, models.RefEdition, rows)


def load(db, ref_path: str = REFERENCE_DB) -> dict:
    if not os.path.isfile(ref_path):
        raise FileNotFoundError(f"reference.db not found at {ref_path} (set RIE_REFERENCE_DB)")
    src = sqlite3.connect(ref_path)
    src.row_factory = sqlite3.Row
    try:
        counts = {"rpl": _load_tariffs(db, src), "nappi": _load_nappi(db, src),
                  "icd10": _load_icd10(db, src)}
        _load_editions(db, src)
        db.commit()
    finally:
        src.close()
    return counts


def main() -> None:
    t0 = time.time()
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        counts = load(db)
        seed(db)                                            # users + statutory (demo pricing skipped)
    print(f"loaded reference from {REFERENCE_DB}: {counts} in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
