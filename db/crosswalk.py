"""COIDA/BHF → RAF-gazette tariff crosswalk — STUB, requires tariff-SME sign-off.

WHY THIS EXISTS
    db/corpus_test.py shows ~69% of tariff billing (R62.94M across the corpus) is
    un-benchmarkable: the claims were billed under COIDA/BHF tariff codes that are not in the RAF
    2026 gazette, so they pay as-billed and land in the R&N (reasonable-&-necessary) review queue.
    The top ~25 codes carry 63% of that exposure. Declaring an equivalence from each such COIDA
    code to a RAF gazette code lets the engine price it under the pay-min rule — collapsing the
    queue and extending automated price control over ~R40M of billing.

HOW IT PLUGS IN (no engine change, conformance preserved)
    A crosswalk entry is purely *reference data*: `apply_crosswalk(book)` makes the RefBook carry
    the RAF rate under the COIDA code as well (an additive alias in book.rpl). The engine
    (engine/, spec/rie_engine.py) is untouched, so the oracle-conformance guarantee still holds.
    To activate confirmed mappings in production, call `apply_crosswalk(book)` at the end of
    server.reference_data.build_refbook (it applies CONFIRMED entries only — see below).

SAFETY — NOTHING HERE IS AUTHORITATIVE
    Every entry is a PROPOSED (or NEEDS_SME / NO_RAF_EQUIVALENT) candidate, grounded in the RAF
    gazette *description* cited in `evidence`. A tariff SME must confirm the clinical equivalence
    (and the correct duration/complexity tier) before promoting status to CONFIRMED. `apply_
    crosswalk` applies CONFIRMED entries only by default, so production pricing never shifts on an
    unverified guess. Pass what_if=True to model the impact of the PROPOSED set.

    python3 db/crosswalk.py     # print the crosswalk + measure PROPOSED recovery on the corpus
"""
from __future__ import annotations

import os
import sqlite3
import sys
from collections import defaultdict
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("RIE_DATABASE_URL", "sqlite:///./rie.db")

from engine import resolve  # noqa: E402
from server.db import SessionLocal  # noqa: E402
from server.reference_data import _norm, build_refbook  # noqa: E402

CONFIRMED = "CONFIRMED"          # SME-signed — safe to apply in production
PROPOSED = "PROPOSED"            # grounded candidate, awaiting SME confirmation (what-if only)
NEEDS_SME = "NEEDS_SME"          # family identified, RAF target still to be chosen
NO_RAF = "NO_RAF_EQUIVALENT"     # genuinely absent from the RAF gazette — stays R&N by design


@dataclass(frozen=True)
class XW:
    coida: str                   # code as billed in the corpus (COIDA/BHF)
    family: str
    corpus_desc: str             # what the corpus says it is
    raf: str | None              # proposed RAF gazette target (None until chosen)
    status: str
    evidence: str                # RAF gazette description/rate supporting the candidate, or why not


# ── the crosswalk (top uncovered families by exposure; see db/corpus_test.py Part A) ──────────
CROSSWALK: list[XW] = [
    # ── consultations — the BHF/COIDA visit tariff family (biggest count, differs from RAF) ──
    XW("0190", "consultation", "New/established patient consultation", "10190", PROPOSED,
       "RAF 10190 GP consultation R587.24 ≈ billed avg R579 — strong rate match; confirm level"),
    XW("0146", "consultation", "Unscheduled emergency consultation", "147", PROPOSED,
       "RAF 147 'after-hours/unscheduled emergency consultation' R489.16 — semantic match"),
    XW("0184", "consultation", "Follow-up visit", None, NEEDS_SME,
       "RAF consult family 145/147/464/10190 — SME to pick the follow-up tier"),
    XW("0181", "consultation", "Visit, new problem/patient, 20 min", None, NEEDS_SME,
       "RAF consult family — map by duration tier (20/30/45 min)"),
    XW("0182", "consultation", "Visit, new problem, ≤30 min", None, NEEDS_SME,
       "RAF consult family — duration tier"),
    XW("0183", "consultation", "Visit, new problem, 45 min", None, NEEDS_SME,
       "RAF consult family — duration tier"),
    XW("0191", "consultation", "Consultation (higher complexity)", None, NEEDS_SME,
       "RAF 10190/464 — billed avg R1,103 exceeds base GP consult; confirm complexity tier"),
    XW("0192", "consultation", "Consultation (higher complexity)", None, NEEDS_SME,
       "RAF 10190/464 — confirm complexity tier"),
    XW("0109", "consultation", "Hospital follow-up visit", None, NEEDS_SME,
       "RAF inpatient/ward-visit code — SME to identify"),
    XW("66201", "consultation", "Observation and screening", None, NEEDS_SME,
       "66xxx is a separate scheme numbering; needs a discipline-specific RAF map"),
    XW("66101", "consultation", "First consultation", None, NEEDS_SME,
       "66xxx scheme — map to RAF first-consult code"),
    XW("66313", "consultation", "Consultation level 3, 45 min", None, NEEDS_SME,
       "66xxx scheme — duration/level tier"),
    XW("66315", "consultation", "Consultation level 4, 60 min", None, NEEDS_SME,
       "66xxx scheme — duration/level tier"),

    # ── hyperbaric-oxygen therapy (high unit cost, ~R9.4M exposure) ──
    XW("4805", "hyperbaric", "Monitoring at the hyperbaric unit", "4804", PROPOSED,
       "RAF 4804 'Monitoring of a patient at the hyperbaric' R1,048.20 — near-identical desc + "
       "adjacent code; RAF tiers 4804/4806/4809 by duration, billed avg R2,115 suggests a higher tier"),
    XW("4821", "hyperbaric", "Routine HBO table (2–2.5 ATA)", None, NEEDS_SME,
       "RAF 41 'hyperbaric pressurisation' R489.81 exists but a 'table' is a bundled multi-session "
       "course; SME must define the session/basis (billed avg R4,625)"),
    XW("4822", "hyperbaric", "Emergency HBO table (2.5–3 ATA)", None, NEEDS_SME,
       "As 4821 — emergency course; SME to define basis vs RAF 41/4806/4809"),

    # ── medico-legal report ──
    XW("0186", "report", "Final medical report", "2712", PROPOSED,
       "RAF 2712 'Clinical interpretation and report' R580; billed avg R1,078 — confirm report scope"),

    # ── orthopaedic surgery ──
    XW("0614", "orthopaedic", "Arthroplasty / debridement, large joint", "909", PROPOSED,
       "RAF 909 'Excision arthroplasty' R5,073.29; billed avg R1,898 (pays as billed) — confirm joint"),
    XW("0465", "orthopaedic", "Fractures involving large joints", None, NEEDS_SME,
       "RAF fracture family 48/49/53 — SME to select reduction type for large joints"),
    XW("0593", "orthopaedic", "Tendon synovectomy", None, NEEDS_SME,
       "RAF 887 'release of digital joint contracture' is the nearest synovectomy — weak; verify"),
    XW("0592", "orthopaedic", "Synovectomy, large joint", None, NEEDS_SME,
       "No clean RAF synovectomy match; SME review"),
    XW("0304", "orthopaedic", "Major wound debridement", None, NEEDS_SME,
       "RAF 746 (muscle/tendon removal) / fasciotomy 5551 — SME to confirm debridement code"),

    # ── other high-exposure procedures ──
    XW("5103", "imaging", "Ultrasound, soft tissue, any region", None, NEEDS_SME,
       "RAF ultrasound is site-specific (240/3627/5101); soft-tissue any-region needs SME pick"),
    XW("2802", "pain", "Procedures for pain relief (peripheral)", None, NEEDS_SME,
       "RAF nerve-block/pain family — SME to identify"),
    XW("1204", "critical-care", "Intensive care, category 1", None, NEEDS_SME,
       "RAF ICU per-diem family — SME to map category ↔ RAF level"),
]


def apply_crosswalk(book, *, what_if: bool = False) -> list[tuple[XW, dict]]:
    """Additively alias each applicable COIDA code onto its RAF target's rate in book.rpl.

    Applies CONFIRMED entries only, unless what_if=True (then PROPOSED too — for impact modelling).
    Skips codes already covered (never overwrites a real reference rate) or whose RAF target is
    absent from the loaded reference. Returns the entries actually applied with the rate map used.
    """
    statuses = {CONFIRMED, PROPOSED} if what_if else {CONFIRMED}
    applied: list[tuple[XW, dict]] = []
    for e in CROSSWALK:
        if e.status not in statuses or not e.raf:
            continue
        src, tgt = _norm(e.coida), _norm(e.raf)
        if src in book.rpl:                    # already benchmarkable — do not shadow real reference
            continue
        if tgt not in book.rpl:                # target missing from the loaded reference edition
            continue
        book.rpl[src] = dict(book.rpl[tgt])    # additive alias → RAF rate (copy, not shared ref)
        applied.append((e, book.rpl[src]))
    return applied


# ── self-demonstration: measure what the PROPOSED crosswalk recovers on the real corpus ───────
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
        book = build_refbook(db, nappi_codes=set())

    by_status = defaultdict(list)
    for e in CROSSWALK:
        by_status[e.status].append(e)
    print(f"\n{'═' * 82}\n  COIDA→RAF TARIFF CROSSWALK (STUB) — {len(CROSSWALK)} entries\n{'═' * 82}")
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
    applied = apply_crosswalk(book, what_if=True)      # model PROPOSED impact
    after = _uncovered(book, billed)

    print(f"\n{'─' * 82}\n  WHAT-IF IMPACT ON THE CORPUS (PROPOSED entries applied)\n{'─' * 82}")
    print(f"\n  {'coida':>6} {'→raf':>6} {'lines':>7} {'exposure benchmarked':>22}  {'raf rate':>10}  effect")
    print("  " + "─" * 80)
    total_moved = 0.0
    for e, rates in applied:
        exp = billed.get(e.coida, 0.0)
        n = lines.get(e.coida, 0)
        rate = rates.get("GP") or min(rates.values())
        avg = exp / n if n else 0
        effect = "reprices ↓" if avg > rate else "pays as billed (benchmarked)"
        total_moved += exp
        print(f"  {e.coida:>6} {e.raf:>6} {n:>7,} R{exp:>19,.2f}  R{rate:>8,.2f}  {effect}")
    print("  " + "─" * 80)
    print(f"\n  uncovered tariff exposure BEFORE : R{base:>16,.2f}")
    print(f"  brought under benchmark (PROPOSED): R{base - after:>16,.2f}   "
          f"({100 * (base - after) / base if base else 0:.1f}% of uncovered)")
    print(f"  remaining uncovered (NEEDS_SME)  : R{after:>16,.2f}")
    print(f"\n  NOTE: PROPOSED mappings are UNVERIFIED candidates — a tariff SME must confirm each")
    print(f"        (clinical equivalence + duration/complexity tier) before status → CONFIRMED.")
    print(f"        apply_crosswalk() applies CONFIRMED only; production pricing is unchanged today.\n")


if __name__ == "__main__":
    main()
