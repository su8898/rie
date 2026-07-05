"""CLI: print the COIDA→RAF tariff crosswalk and measure PROPOSED impact on the real corpus.

The crosswalk data + apply logic live in server.crosswalk (the production reference-data layer,
now wired into build_refbook — CONFIRMED entries only). This is the analyst-facing runner: it
lists every entry by status and, when the corpus is present, models what the PROPOSED set would
bring under benchmark control.

    python3 db/crosswalk.py
    RIE_CORPUS_DB=/path/to/claims.db   (default: ~/Desktop/old_cie_data/claims.db)
"""
from __future__ import annotations

import os
import sqlite3
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("RIE_DATABASE_URL", "sqlite:///./rie.db")

from engine import resolve  # noqa: E402
from server.crosswalk import (  # noqa: E402
    CONFIRMED, CROSSWALK, NEEDS_SME, NO_RAF, PROPOSED, apply_crosswalk,
)
from server.db import SessionLocal  # noqa: E402
from server.reference_data import build_refbook  # noqa: E402


def _corpus_tariff_exposure(claims_db: str):
    con = sqlite3.connect(claims_db)
    con.row_factory = sqlite3.Row
    billed: dict[str, float] = defaultdict(float)
    lines: dict[str, int] = defaultdict(int)
    for r in con.execute("SELECT tariff, amount_claimed FROM claim_lines "
                         "WHERE type='1' AND tariff!='' AND tariff IS NOT NULL"):
        code = (r["tariff"] or "").strip()
        if not code or code.upper() == "NULL":
            continue
        try:
            amt = float(str(r["amount_claimed"]).replace(",", "") or 0)
        except ValueError:
            amt = 0.0
        billed[code] += amt
        lines[code] += 1
    con.close()
    return billed, lines


def _uncovered(book, billed) -> float:
    return sum(v for c, v in billed.items() if resolve(book, "TARIFF", c)[0] is None)


def main() -> None:
    claims_db = os.environ.get("RIE_CORPUS_DB", os.path.expanduser("~/Desktop/old_cie_data/claims.db"))
    with SessionLocal() as db:
        book = build_refbook(db, nappi_codes=set())    # already applies CONFIRMED crosswalk

    by_status = defaultdict(list)
    for e in CROSSWALK:
        by_status[e.status].append(e)
    print(f"\n{'═' * 82}\n  COIDA→RAF TARIFF CROSSWALK — {len(CROSSWALK)} entries "
          f"(wired into build_refbook; CONFIRMED applied live)\n{'═' * 82}")
    for st in (CONFIRMED, PROPOSED, NEEDS_SME, NO_RAF):
        es = by_status.get(st, [])
        if not es:
            continue
        print(f"\n  {st}  ({len(es)})")
        for e in es:
            tgt = f"→ RAF {e.raf}" if e.raf else "→ (target TBD)"
            print(f"    {e.coida:>6} {tgt:<12} {e.family:<14} {e.corpus_desc[:34]:34}")
            print(f"           ↳ {e.evidence}")

    if not os.path.isfile(claims_db):
        print(f"\n  (corpus {claims_db} not present — skipping impact measurement)\n")
        return

    billed, lines = _corpus_tariff_exposure(claims_db)
    base = _uncovered(book, billed)
    applied = apply_crosswalk(book, what_if=True)      # model PROPOSED impact on top of CONFIRMED
    after = _uncovered(book, billed)

    print(f"\n{'─' * 82}\n  WHAT-IF IMPACT ON THE CORPUS (PROPOSED entries applied)\n{'─' * 82}")
    print(f"\n  {'coida':>6} {'→raf':>6} {'lines':>7} {'exposure benchmarked':>22}  {'raf rate':>10}  effect")
    print("  " + "─" * 80)
    for e, rates in applied:
        exp = billed.get(e.coida, 0.0)
        n = lines.get(e.coida, 0)
        rate = rates.get("GP") or min(rates.values())
        avg = exp / n if n else 0
        effect = "reprices ↓" if avg > rate else "pays as billed (benchmarked)"
        print(f"  {e.coida:>6} {e.raf:>6} {n:>7,} R{exp:>19,.2f}  R{rate:>8,.2f}  {effect}")
    print("  " + "─" * 80)
    print(f"\n  uncovered tariff exposure BEFORE : R{base:>16,.2f}")
    print(f"  brought under benchmark (PROPOSED): R{base - after:>16,.2f}   "
          f"({100 * (base - after) / base if base else 0:.1f}% of uncovered)")
    print(f"  remaining uncovered (NEEDS_SME)  : R{after:>16,.2f}")
    print(f"\n  NOTE: PROPOSED mappings are UNVERIFIED candidates — a tariff SME must confirm each")
    print(f"        (clinical equivalence + duration/complexity tier) before status → CONFIRMED.")
    print(f"        build_refbook applies CONFIRMED only, so production pricing is unchanged today.\n")


if __name__ == "__main__":
    main()
