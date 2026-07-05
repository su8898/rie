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
    XW("0190", "consultation", "New/established patient consultation", "10190", CONFIRMED,
       "CONFIRMED 2026-07-05: RAF 10190 GP consultation R587.24 ≈ billed avg R579 — accepted"),
    XW("0146", "consultation", "Unscheduled emergency consultation", "147", CONFIRMED,
       "CONFIRMED 2026-07-05: RAF 147 'after-hours/unscheduled emergency consultation' R489.16 — accepted"),
    XW("0184", "consultation", "Follow-up visit", "10190", PROPOSED,
       "RAF 10190 GP consultation R587.24 — RAF prices a single GP consult tariff (no duration / "
       "follow-up sub-tiers), so all COIDA visit variants benchmark against it"),
    XW("0181", "consultation", "Visit, new problem/patient, 20 min", "10190", PROPOSED,
       "RAF 10190 GP consultation R587.24 (RAF does not tier the GP consult by duration)"),
    XW("0182", "consultation", "Visit, new problem, ≤30 min", "10190", PROPOSED,
       "RAF 10190 GP consultation R587.24 (no duration tier in the RAF GP schedule)"),
    XW("0183", "consultation", "Visit, new problem, 45 min", "10190", PROPOSED,
       "RAF 10190 GP consultation R587.24 (no duration tier in the RAF GP schedule)"),
    XW("0191", "consultation", "Consultation (higher complexity)", "10190", PROPOSED,
       "RAF 10190 GP consultation R587.24; billed avg R1,103 would reprice down — confirm whether a "
       "specialist/complex consult (e.g. RAF 464 R960.85) applies instead"),
    XW("0192", "consultation", "Consultation (higher complexity)", "10190", PROPOSED,
       "RAF 10190 GP consultation R587.24; billed avg R1,175 would reprice down — see 0191 note"),
    XW("0109", "consultation", "Hospital follow-up visit", "10190", PROPOSED,
       "RAF 10190 GP consultation R587.24 ≈ billed avg R544; if billed as inpatient management, RAF "
       "1221 'professional fee for managing a patient' R1,048.20 may apply — SME to confirm setting"),
    XW("66201", "occupational-therapy", "Observation and screening", "66207", PROPOSED,
       "66xxx = Occupational Therapist schedule; RAF 66207 'specific evaluation for dysfunction' "
       "R670.08. LOW CONFIDENCE: billed avg R156 is far lower, suggesting a screening/measurement "
       "item (e.g. RAF 66213 R148.91) — OT SME to pick"),
    XW("66101", "occupational-therapy", "First consultation", "66207", PROPOSED,
       "RAF 66207 'specific evaluation for dysfunction' R670.08 (OT initial evaluation); RAF 66136 "
       "in-depth eval R3,248 if extensive — OT SME to pick"),
    XW("66313", "occupational-therapy", "Treatment level 3, 45 min", "66407", PROPOSED,
       "RAF 66407 'on level three' R536.06 ≈ billed avg R553 (OT graded-treatment series 66309 L1 / "
       "66311 L2 / 66317 L5; the corpus bills the L3/L4 rungs the gazette omits)"),
    XW("66315", "occupational-therapy", "Treatment level 4, 60 min", "66317", PROPOSED,
       "RAF 66317 'on level five (90 min)' R1,191.25 is the nearest gazetted rung above the ungazetted "
       "level four; billed avg R735 → would pay as billed — OT SME to confirm the level"),

    # ── hyperbaric-oxygen therapy (high unit cost, ~R9.4M exposure) ──
    XW("4805", "hyperbaric", "Monitoring at the hyperbaric unit", "4804", CONFIRMED,
       "CONFIRMED 2026-07-05: RAF 4804 'Monitoring of a patient at the hyperbaric' R1,048.20 accepted "
       "as the base-tier equivalent (billed avg R2,115 → repriced); revisit if a longer-duration "
       "tier 4806/4809 should apply"),
    XW("4821", "hyperbaric", "Routine HBO table (2–2.5 ATA)", "4809", PROPOSED,
       "RAF hyperbaric monitoring tiers 4804/4806/4809/4810 by duration; 4809 R3,144.60 for a routine "
       "extended session. LOW CONFIDENCE: a 'table' (treatment profile) may bill separately from "
       "monitoring — HBO SME to confirm the tier / whether a technical-table code (e.g. 4826) applies"),
    XW("4822", "hyperbaric", "Emergency HBO table (2.5–3 ATA)", "4810", PROPOSED,
       "RAF 4810 'monitoring of a patient at the hyperbaric' R6,638.60 — highest/longest tier for an "
       "emergency deep table; billed avg R4,667 → pays as billed — HBO SME to confirm tier"),

    # ── medico-legal report ──
    XW("0186", "report", "Final medical report", "2712", CONFIRMED,
       "CONFIRMED 2026-07-05: RAF 2712 'Clinical interpretation and report' R580 accepted as the "
       "equivalent for the final medical report (billed avg R1,078 → repriced to tariff)"),

    # ── orthopaedic surgery ──
    XW("0614", "orthopaedic", "Arthroplasty / debridement, large joint", "909", CONFIRMED,
       "CONFIRMED 2026-07-05: RAF 909 'Excision arthroplasty' R5,073.29 accepted (billed avg R1,898 → pays as billed)"),
    XW("0465", "orthopaedic", "Fractures involving large joints", "387", PROPOSED,
       "RAF 387 'Fracture (reduction under general anaesthetic)' R3,277.37 (generic reduction); the "
       "specific large-joint code (387/439/447/448 by bone) — SME to refine"),
    XW("0593", "orthopaedic", "Tendon synovectomy", None, NEEDS_SME,
       "No genuine synovectomy code in the RAF gazette (nearest, 887 'release of digital joint "
       "contracture', is not equivalent) — SME to source or negotiate a rate"),
    XW("0592", "orthopaedic", "Synovectomy, large joint", None, NEEDS_SME,
       "No genuine synovectomy code in the RAF gazette — SME to source or negotiate a rate"),
    XW("0304", "orthopaedic", "Major wound debridement", "10304", CONFIRMED,
       "CONFIRMED 2026-07-05: RAF 10304 'Major debridement of wound, sloughectomy' R1,747.00 — exact "
       "description match, adjacent code (billed avg R777 → pays as billed)"),

    # ── other high-exposure procedures ──
    XW("5103", "imaging", "Ultrasound, soft tissue, any region", "60200", CONFIRMED,
       "CONFIRMED 2026-07-05: RAF 60200 'Ultrasound upper limb — soft tissue, any region' R1,758.80 "
       "accepted for soft-tissue ultrasound; revisit if lower-limb studies should route to 70200"),
    XW("2802", "pain", "Procedures for pain relief (peripheral)", "2801", CONFIRMED,
       "CONFIRMED 2026-07-05: RAF 2801 R1,572.30 — gazette text reads 'or 2802 alcohol injection in "
       "peripheral nerves for pain'; adjacent code (billed avg R806 → pays as billed)"),
    XW("1204", "critical-care", "Intensive care, category 1", "1221", CONFIRMED,
       "CONFIRMED 2026-07-05: RAF 1221 'Professional fee for managing a patient' R1,048.20 ≈ billed "
       "avg R1,049 accepted as the ICU category-1 daily fee; revisit if RAF gazettes a distinct ICU per-diem"),
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
