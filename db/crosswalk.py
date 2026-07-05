"""CLI: inspect the COIDA→RAF tariff crosswalk and model its impact on the real corpus.

The crosswalk data + apply logic live in server.crosswalk (the production reference-data layer,
wired into build_refbook — CONFIRMED entries only). This is the analyst-facing runner.

    python3 db/crosswalk.py                # list entries by status + PROPOSED exposure what-if
    python3 db/crosswalk.py --activation   # run the whole corpus through the engine twice
                                           #   (production today vs. all PROPOSED → CONFIRMED)

    RIE_CORPUS_DB=/path/to/claims.db       (default: ~/Desktop/old_cie_data/claims.db)
"""
from __future__ import annotations

import os
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # repo root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))                    # db/ (corpus_test)

os.environ.setdefault("RIE_DATABASE_URL", "sqlite:///./rie.db")

from engine import adjudicate_line, process_claim, resolve  # noqa: E402
from server.crosswalk import (  # noqa: E402
    CONFIRMED, CROSSWALK, NEEDS_SME, NO_RAF, PROPOSED, apply_crosswalk,
)
from server.db import SessionLocal  # noqa: E402
from server.reference_data import build_refbook, build_ruleset  # noqa: E402

TODAY = date(2026, 7, 5)
CORPUS_DB = os.environ.get("RIE_CORPUS_DB", os.path.expanduser("~/Desktop/old_cie_data/claims.db"))
XCODES = {e.coida for e in CROSSWALK if e.status == PROPOSED}    # what --activation would confirm


def _R(x: float) -> str:
    return f"R{x:,.2f}"


def _pct(h: int, t: int) -> str:
    return f"{100 * h / t:.1f}%" if t else "—"


# ── the crosswalk table (always printed) ──────────────────────────────────────────────────────
def print_table() -> None:
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


# ── default view: PROPOSED exposure what-if (fast, tariff-only) ────────────────────────────────
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


def _uncovered_exposure(book, billed) -> float:
    return sum(v for c, v in billed.items() if resolve(book, "TARIFF", c)[0] is None)


def exposure_whatif(claims_db: str) -> None:
    with SessionLocal() as db:
        book = build_refbook(db, nappi_codes=set())     # CONFIRMED-only baseline
    billed, lines = _corpus_tariff_exposure(claims_db)
    base = _uncovered_exposure(book, billed)
    applied = apply_crosswalk(book, what_if=True)
    if not applied:
        print(f"\n  All grounded (PROPOSED) mappings are CONFIRMED and priced live; R{base:,.2f} of")
        print(f"  tariff exposure remains uncovered in NEEDS_SME entries (targets still to be set).\n")
        return
    after = _uncovered_exposure(book, billed)

    print(f"\n{'─' * 82}\n  WHAT-IF EXPOSURE (PROPOSED entries applied)\n{'─' * 82}")
    print(f"\n  {'coida':>6} {'→raf':>6} {'lines':>7} {'exposure benchmarked':>22}  {'raf rate':>10}  effect")
    print("  " + "─" * 80)
    for e, rates in applied:
        exp, n = billed.get(e.coida, 0.0), lines.get(e.coida, 0)
        rate = rates.get("GP") or min(rates.values())
        effect = "reprices ↓" if (exp / n if n else 0) > rate else "pays as billed (benchmarked)"
        print(f"  {e.coida:>6} {e.raf:>6} {n:>7,} R{exp:>19,.2f}  R{rate:>8,.2f}  {effect}")
    print("  " + "─" * 80)
    print(f"\n  uncovered tariff exposure BEFORE : R{base:>16,.2f}")
    print(f"  brought under benchmark (PROPOSED): R{base - after:>16,.2f}   "
          f"({100 * (base - after) / base if base else 0:.1f}% of uncovered)")
    print(f"  remaining uncovered (NEEDS_SME)  : R{after:>16,.2f}")
    print(f"\n  (run with --activation to price the whole corpus through the engine both ways)\n")


# ── --activation view: whole corpus through the engine, production vs. all-CONFIRMED ───────────
def _run_corpus(claims, book, rs) -> dict:
    m = dict(billed=0.0, payable=0.0, saving=0.0, repriced=0, uncov=0, thit=0, tlines=0)
    disp: Counter = Counter()
    per = {c: dict(lines=0, billed=0.0, saving=0.0) for c in XCODES}
    for c in claims:
        seen: set = set()
        for l in c.lines:
            lr = adjudicate_line(c, l, book, rs, "GP", seen, set())
            m["billed"] += l.amount
            m["payable"] += lr.payable
            covered = resolve(book, l.kind, l.code)[0] is not None
            if l.kind == "TARIFF":
                m["tlines"] += 1
                m["thit"] += covered
            if not covered:
                m["uncov"] += 1
            elif "BILLED_OVER_REFERENCE" in lr.reasons and lr.payable < l.amount:
                m["repriced"] += 1
                m["saving"] += l.amount - lr.payable
            if l.code in per:
                per[l.code]["lines"] += 1
                per[l.code]["billed"] += l.amount
                per[l.code]["saving"] += max(0.0, l.amount - lr.payable)
        disp[process_claim(c, [], book, rs, TODAY, provider_tier="GP")["disposition"]] += 1
    m["disp"], m["per"] = disp, per
    return m


def activation(claims_db: str) -> None:
    if not XCODES:
        print(f"\n{'─' * 82}\n  ACTIVATION IMPACT\n{'─' * 82}")
        print("  No PROPOSED entries remain — all grounded mappings are CONFIRMED and priced live by")
        print("  build_refbook. Remaining uncovered exposure sits in NEEDS_SME entries (targets TBD);")
        print("  run without --activation for the current live coverage.\n")
        return

    import corpus_test as ct                              # heavy import — only for this view

    claims, nappi_codes, _ = ct.load_corpus()
    with SessionLocal() as db:
        book = build_refbook(db, nappi_codes=nappi_codes)   # CONFIRMED-only = production today
        rs = build_ruleset(db)
    base = _run_corpus(claims, book, rs)
    apply_crosswalk(book, what_if=True)                  # promote the 5 PROPOSED → CONFIRMED
    act = _run_corpus(claims, book, rs)

    print(f"\n{'─' * 82}\n  ACTIVATION IMPACT — all {len(XCODES)} PROPOSED promoted to CONFIRMED\n{'─' * 82}")
    print(f"  corpus: {len(claims):,} claims · {sum(len(c.lines) for c in claims):,} lines "
          f"({base['tlines']:,} tariff)\n")
    rows = [
        ("tariff lines resolving",
         f"{base['thit']:,} ({_pct(base['thit'], base['tlines'])})",
         f"{act['thit']:,} ({_pct(act['thit'], act['tlines'])})", f"+{act['thit'] - base['thit']:,}"),
        ("uncovered lines → R&N review", f"{base['uncov']:,}", f"{act['uncov']:,}",
         f"−{base['uncov'] - act['uncov']:,}"),
        ("lines repriced (pay-min)", f"{base['repriced']:,}", f"{act['repriced']:,}",
         f"+{act['repriced'] - base['repriced']:,}"),
        ("repricing leakage caught", _R(base['saving']), _R(act['saving']),
         "+" + _R(act['saving'] - base['saving'])),
        ("engine payable (what RAF pays)", _R(base['payable']), _R(act['payable']),
         "−" + _R(base['payable'] - act['payable'])),
        ("dispositions CLEAN / ADJUSTED",
         f"{base['disp']['CLEAN']:,}/{base['disp']['ADJUSTED']:,}",
         f"{act['disp']['CLEAN']:,}/{act['disp']['ADJUSTED']:,}", ""),
    ]
    print(f"  {'metric':32} {'production today':>20} {'if CONFIRMED':>20}   Δ")
    print("  " + "─" * 88)
    for label, b, a, d in rows:
        print(f"  {label:32} {b:>20} {a:>20}   {d}")

    print(f"\n  per confirmed entry:")
    print(f"    {'coida→raf':>12} {'lines':>7} {'exposure benchmarked':>22} {'new leakage caught':>20}")
    print("    " + "─" * 64)
    by_code = {e.coida: e for e in CROSSWALK}
    for code in sorted(XCODES, key=lambda c: -act['per'][c]['billed']):
        p = act['per'][code]
        print(f"    {code + '→' + by_code[code].raf:>12} {p['lines']:>7,} "
              f"{_R(p['billed']):>22} {_R(p['saving']):>20}")

    moved = base['uncov'] - act['uncov']
    exp = sum(act['per'][c]['billed'] for c in XCODES)
    print(f"\n  headline: {moved:,} lines / {_R(exp)} move from the R&N review queue into automated")
    print(f"  benchmarking; {_R(act['saving'] - base['saving'])} additional leakage caught; RAF pays "
          f"{_R(base['payable'] - act['payable'])} less.")
    print(f"\n  NOTE: simulation only — nothing is CONFIRMED, so build_refbook applies none of this.")
    print(f"        The largest savings (0186, 4805) come from the largest rate gaps — confirm those")
    print(f"        first and most carefully, as a big gap can mean the codes are NOT equivalent.\n")


def main() -> None:
    print_table()
    if not os.path.isfile(CORPUS_DB):
        print(f"\n  (corpus {CORPUS_DB} not present — skipping impact measurement)\n")
        return
    if "--activation" in sys.argv:
        activation(CORPUS_DB)
    else:
        exposure_whatif(CORPUS_DB)


if __name__ == "__main__":
    main()
