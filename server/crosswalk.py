"""COIDA/BHF → RAF-gazette tariff crosswalk (reference-data layer).

Many claims are billed under COIDA/BHF tariff codes that are absent from the RAF 2026 gazette, so
the engine can't price them (db/corpus_test.py: ~69% of tariff billing is un-benchmarkable). A
crosswalk entry declares a COIDA code equivalent to a RAF gazette code; `apply_crosswalk` then
makes the RefBook carry the RAF rate under the COIDA code too, so the engine prices it under the
pay-min rule. This is purely *additive reference data* — the engine (engine/, spec/rie_engine.py)
is untouched, so oracle-conformance is preserved.

SAFETY — every entry is a candidate requiring tariff-SME sign-off. Status ladder:
CONFIRMED → PROPOSED → NEEDS_SME → NO_RAF_EQUIVALENT. `apply_crosswalk` applies CONFIRMED entries
only by default (pass what_if=True to also apply PROPOSED, for impact modelling). build_refbook
calls it with the default, so production pricing shifts only once an SME promotes an entry to
CONFIRMED — merely drafting/expanding the crosswalk never moves a live price.

See db/crosswalk.py to print the table and measure PROPOSED impact on the real corpus.
"""
from __future__ import annotations

from dataclasses import dataclass

CONFIRMED = "CONFIRMED"          # SME-signed — applied in production
PROPOSED = "PROPOSED"            # grounded candidate, awaiting SME confirmation (what-if only)
NEEDS_SME = "NEEDS_SME"          # family identified, RAF target still to be chosen
NO_RAF = "NO_RAF_EQUIVALENT"     # genuinely absent from the RAF gazette — stays R&N by design


def _norm(code: str) -> str:
    """Tariff-code normalisation — mirrors engine.reference.resolve / reference_data._norm."""
    return code.lstrip("0") or "0"


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
    XW("4805", "hyperbaric", "Monitoring at the hyperbaric unit", "4804", CONFIRMED,
       "CONFIRMED 2026-07-05: RAF 4804 'Monitoring of a patient at the hyperbaric' R1,048.20 accepted "
       "as the base-tier equivalent (billed avg R2,115 → repriced); revisit if a longer-duration "
       "tier 4806/4809 should apply"),
    XW("4821", "hyperbaric", "Routine HBO table (2–2.5 ATA)", None, NEEDS_SME,
       "RAF 41 'hyperbaric pressurisation' R489.81 exists but a 'table' is a bundled multi-session "
       "course; SME must define the session/basis (billed avg R4,625)"),
    XW("4822", "hyperbaric", "Emergency HBO table (2.5–3 ATA)", None, NEEDS_SME,
       "As 4821 — emergency course; SME to define basis vs RAF 41/4806/4809"),

    # ── medico-legal report ──
    XW("0186", "report", "Final medical report", "2712", CONFIRMED,
       "CONFIRMED 2026-07-05: RAF 2712 'Clinical interpretation and report' R580 accepted as the "
       "equivalent for the final medical report (billed avg R1,078 → repriced to tariff)"),

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
