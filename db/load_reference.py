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
  ref_tariffs -> ref_code_rule  the tariff's own billing rules (ported from CIE): a code whose
                                description limits it to once per encounter, and the standard time
                                modifiers the tariff carries (billed in minutes, priced by ladder).
                                Rules an administrator added by hand are kept.
  (CIE list)  -> ref_non_bench  codes that must not be priced at a flat rate (percentage
                                modifiers, cost-of-material codes): held for review, not repriced.

This also creates the tables and seeds users + statutory config, so it is a self-contained
deploy-init:  python3 db/load_reference.py   (target DB = RIE_DATABASE_URL).
"""
from __future__ import annotations

import os
import re
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import delete, insert, select  # noqa: E402

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


# Tariff-description phrasings that limit a code to once per encounter (kept conservative — the
# descriptions are OCR text; "once per level/week/annum" are NOT per-encounter limits). From CIE.
FREQ_ONCE_RE = re.compile(r"(use (code )?once only|to be charged once only|"
                          r"chargeable once per 24 hours|once per (service|session))", re.IGNORECASE)
# A once-only phrase the OCR bled in from a neighbouring code (3575 carries the wording of 3604).
# Excluded from the seed; add it by hand under Admin -> Coding rules if the gazette confirms it.
ONCE_ONLY_OCR_FALSE_POSITIVES = {"3575"}
# Codes that must not be priced at a flat rate per unit (from CIE's modifier rules): a percentage
# of another fee, a cost-of-material code reimbursed at cost, or not a priced service at all. A
# line on one of these has no benchmark by design and goes to R&N review (REFERENCE_UNRESOLVED).
NON_BENCHMARKABLE = {
    "0005": "modifier (multiple procedures)", "0006": "modifier (visiting specialist)",
    "0008": "assistant (% of surgeon fee)", "0009": "assistant (% of surgeon fee)",
    "0074": "modifier (endoscopic base)", "0133": "add-on (per 15 min)",
    "8007": "assistant (% of fee)", "8008": "after-hours modifier", "8010": "open-reduction modifier",
    "0201": "cost of material", "00090": "radiology consumables (cost)", "00390": "CT contrast (cost)",
    "00490": "MR contrast (cost)", "39300": "X-ray films (cost)", "72939": "cost of material",
    "88301": "cost of material", "1830": "hearing aid (global supply)",
    "0002": "written report", "6999": "unlisted (comparable code)",
    "0004": "discipline code", "0084": "discipline code",
    "0026": "modifier (one-lung ventilation)",
}
# The standard time modifiers (SASA coding guidelines; CIE's modifier-pricing rules). The billed
# quantity is MINUTES and the tariff rate is the block value. Seeded only for codes the tariff carries.
STANDARD_CODE_RULES = {
    "11": ("TIME_BLOCK", 30.0, "emergency theatre time — one block per half-hour or part thereof"),
    "23": ("TIME_ANAES", 0.0, "anaesthetic time — per 15 minutes or part; 1.5x after the first hour"),
    "39": ("TIME_FIRST_HOUR", 0.0, "anaesthetic time — first hour, then a third per 15 minutes or part"),
    "18": ("PCT_OF_TIME", 0.5, "adds 50% of the anaesthetic time billed with it"),
    "19": ("PCT_OF_TIME", 0.5, "adds 50% of the anaesthetic time billed with it"),
}


def _load_code_rules(db, src) -> int:
    rules: dict = {}
    for r in src.execute("SELECT norm_code, description FROM ref_tariffs WHERE norm_code IS NOT NULL"):
        code = _norm(r["norm_code"])
        m = FREQ_ONCE_RE.search(r["description"] or "")
        if m and code not in ONCE_ONLY_OCR_FALSE_POSITIVES:
            rules.setdefault(code, {"code": code, "rule": "ONCE_PER_ENCOUNTER", "param": 0.0,
                                    "basis": f"tariff description: \u201c{m.group(0)}\u201d",
                                    "origin": "tariff", "created_by": "loader"})
        elif code in STANDARD_CODE_RULES:
            rule, param, basis = STANDARD_CODE_RULES[code]
            rules.setdefault(code, {"code": code, "rule": rule, "param": param, "basis": basis,
                                    "origin": "standard", "created_by": "loader"})
    manual = set(db.scalars(select(models.RefCodeRule.code)
                            .where(models.RefCodeRule.origin == "manual")))
    db.execute(delete(models.RefCodeRule).where(models.RefCodeRule.origin != "manual"))
    rows = [v for k, v in rules.items() if k not in manual]      # a hand-set rule wins
    if rows:
        _bulk(db, models.RefCodeRule, rows)
    return len(rows)


def _load_non_benchmarkable(db) -> int:
    """Add the flat-rate exclusions that are not already listed (codes stored normalised). Rows
    an operator added are left alone; nothing is removed."""
    have = set(db.scalars(select(models.RefNonBench.code)))
    new = sorted({_norm(c) for c in NON_BENCHMARKABLE} - {_norm(c) for c in have})
    if new:
        _bulk(db, models.RefNonBench, [{"code": c} for c in new])
    return len(new)


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
                  "icd10": _load_icd10(db, src), "code_rules": _load_code_rules(db, src),
                  "non_benchmarkable": _load_non_benchmarkable(db)}
        _load_editions(db, src)
        db.commit()
    finally:
        src.close()
    return counts


def ensure_schema() -> None:
    """Bring the database to head via Alembic (the production schema path — the app emits no DDL).

    Handles three states: a fresh DB is created by `upgrade head`; a DB already under Alembic has
    its pending migrations applied; a pre-existing schema built by create_all (no alembic_version)
    is *adopted* with `stamp head` rather than re-created. Falls back to create_all only when
    Alembic isn't installed, so local dev / tests stay hermetic."""
    try:
        from alembic import command
        from alembic.config import Config
        from sqlalchemy import inspect
    except ImportError:
        Base.metadata.create_all(engine)
        return
    cfg = Config(os.path.join(_ROOT, "alembic.ini"))
    insp = inspect(engine)
    if insp.has_table("app_users") and not insp.has_table("alembic_version"):
        command.stamp(cfg, "head")                      # adopt a schema previously built by create_all
    else:
        command.upgrade(cfg, "head")                    # fresh -> create; migrated -> apply pending


def main() -> None:
    t0 = time.time()
    ensure_schema()
    with SessionLocal() as db:
        counts = load(db)
        seed(db)                                            # users + statutory (demo pricing skipped)
    print(f"loaded reference from {REFERENCE_DB}: {counts} in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
