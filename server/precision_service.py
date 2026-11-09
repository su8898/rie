"""Precision / recall governance — the close-the-loop feedback layer (domain-logic §11).

Decided cases are ground truth. For every signal we measure its **substantiation rate** (precision)
against those labels with a Wilson score interval, and recommend its place in the promotion
lifecycle SHADOW -> ADVISORY -> SCORED: promotion to SCORED needs a **Wilson lower bound >= 60%**
(the §11 measured-precision floor), and a SCORED signal that drops below the floor is flagged for
demotion. Recall is estimated from a blind GREEN sample: GREEN claims later found adverse are
false negatives, and the Wilson upper bound of that miss rate gives a conservative recall floor.
Grounded (law-cited) signals are always SCORED and exempt from the floor.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from engine.reasons import MODE, R
from engine.vocab import Maturity

from . import models

Z95 = 1.959963984540054                                # 95% two-sided
SCORED_FLOOR = 0.60                                    # Wilson-lower floor to promote to SCORED (§11)
MIN_LABELED = 5                                        # too few labels to judge a signal
ADVERSE = {"CONFIRMED_FRAUD", "ADJUSTED", "REFERRED_LEGAL"}   # case verdict -> the signal was right
BENIGN = {"CLEARED", "NO_ACTION"}                            # case verdict -> false positive


def wilson(k: int, n: int, z: float = Z95) -> dict:
    """Wilson score interval for a binomial proportion k/n (stdlib, deterministic)."""
    if n <= 0:
        return {"n": 0, "k": k, "point": None, "lower": None, "upper": None}
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / denom
    return {"n": n, "k": k, "point": round(p, 4),
            "lower": round(max(0.0, centre - half), 4), "upper": round(min(1.0, centre + half), 4)}


def _claim_labels(db: Session) -> dict[str, str]:
    """claim_id -> ADVERSE | BENIGN from closed-case verdicts (adverse wins if a claim has several)."""
    labels: dict[str, str] = {}
    for c in db.scalars(select(models.Case).where(models.Case.status == "CLOSED")
                        .order_by(models.Case.id)):
        if not c.claim_id or c.verdict is None:
            continue
        if c.verdict in ADVERSE:
            labels[c.claim_id] = "ADVERSE"
        elif c.verdict in BENIGN and labels.get(c.claim_id) != "ADVERSE":
            labels[c.claim_id] = "BENIGN"
    return labels


def _recommend(current: str, meta, w: dict) -> str:
    if meta is not None and meta.maturity is Maturity.GROUNDED:
        return "SCORED"                                # law-cited hard gates are always scored
    if (w["n"] or 0) < MIN_LABELED:
        return current                                 # insufficient labels -> hold current mode
    if w["lower"] is not None and w["lower"] >= SCORED_FLOOR:
        return "SCORED"                                # measured-precision floor met
    return "ADVISORY"                                  # measured but below the 60% Wilson-lower floor


def precision_by_signal(db: Session) -> list[dict]:
    labels = _claim_labels(db)
    agg: dict = defaultdict(lambda: {"fired": 0, "labeled": 0, "adverse": 0})
    for det in db.scalars(select(models.Determination)
                          .where(models.Determination.id.in_(models.latest_determination_ids()))):
        signals = set(det.reasons or []) | set(det.shadow_signals or [])   # one firing per claim, latest verdict
        lab = labels.get(det.claim_id)
        for code in signals:
            agg[code]["fired"] += 1
            if lab:
                agg[code]["labeled"] += 1
                agg[code]["adverse"] += int(lab == "ADVERSE")
    out = []
    for code, s in sorted(agg.items()):
        meta = R.get(code)
        w = wilson(s["adverse"], s["labeled"])
        current = MODE.get(code).name if code in MODE else "SCORED"
        out.append({
            "signal": code,
            "category": meta.category.name if meta else None,
            "maturity": meta.maturity.name if meta else None,
            "current_mode": current, "recommended_mode": _recommend(current, meta, w),
            "fired": s["fired"], "labeled": s["labeled"], "substantiated": s["adverse"],
            "substantiation": w["point"], "wilson_lower": w["lower"], "wilson_upper": w["upper"],
        })
    return out


def promotions(db: Session) -> list[dict]:
    """Only the signals whose measured mode differs from their current mode — the ADMIN action list."""
    rows = []
    for r in precision_by_signal(db):
        if r["recommended_mode"] != r["current_mode"]:
            order = {"SHADOW": 0, "ADVISORY": 1, "SCORED": 2}
            r["action"] = ("PROMOTE" if order[r["recommended_mode"]] > order[r["current_mode"]]
                           else "DEMOTE")
            rows.append(r)
    return rows


def _green_claims(db: Session) -> list[str]:
    return [d.claim_id for d in
            db.scalars(select(models.Determination).where(models.Determination.band == "GREEN")
                       .where(models.Determination.id.in_(models.latest_determination_ids()))
                       .order_by(models.Determination.claim_id))]


def recall_qa_sample(db: Session, n: int = 20) -> dict:
    """A deterministic spread of auto-cleared (GREEN) claims into blind review (§11 recall QA)."""
    greens = _green_claims(db)
    step = max(1, len(greens) // n) if n else 1
    sample = greens[::step][:n] if n else greens
    return {"population": len(greens), "sample_size": len(sample), "claims": sample}


def draw_recall_qa(db: Session, user: dict, n: int = 30) -> dict:
    """Draw the recall sample into the Cases module as blind-QA REVIEW cases: GREEN (auto-cleared)
    claims a reviewer decides blind, whose closed verdict becomes ground truth for the recall
    estimate (§11 close-the-loop). Skips claims that already carry an open REVIEW case so repeated
    draws never duplicate."""
    from . import cases_service                         # lazy import: avoid a service-layer cycle
    sample = recall_qa_sample(db, n=n)["claims"]
    open_states = ("OPEN", "IN_REVIEW", "ESCALATED")
    existing = {c.claim_id for c in db.scalars(
        select(models.Case).where(models.Case.lane == "REVIEW",
                                  models.Case.status.in_(open_states))) if c.claim_id}
    drawn = 0
    for cid in sample:
        if cid in existing:
            continue
        cases_service.open_case(db, user, lane="REVIEW",
                                reason="Blind QA — recall sample (§11)",
                                claim_id=cid, priority=4)
        drawn += 1
    return {"drawn": drawn, "sampled": len(sample), "skipped": len(sample) - drawn}


def recall_estimate(db: Session) -> dict:
    """From GREEN claims already case-reviewed: the miss rate (false negatives) + a conservative
    recall floor (1 - Wilson upper bound of the miss rate)."""
    labels = _claim_labels(db)
    reviewed = [(cid, labels[cid]) for cid in set(_green_claims(db)) if cid in labels]
    misses = sum(1 for _, lab in reviewed if lab == "ADVERSE")
    w = wilson(misses, len(reviewed))
    return {"reviewed": len(reviewed), "misses": misses, "miss_rate": w["point"],
            "miss_rate_wilson_upper": w["upper"],
            "recall_floor": round(1 - w["upper"], 4) if w["upper"] is not None else None}


def labels_export(db: Session) -> list[dict]:
    """The labels.csv content — one row per closed-case ground-truth label."""
    out = []
    for c in db.scalars(select(models.Case).where(models.Case.status == "CLOSED")
                        .order_by(models.Case.id)):
        if not c.claim_id or c.verdict is None:
            continue
        label = "ADVERSE" if c.verdict in ADVERSE else "BENIGN" if c.verdict in BENIGN else "OTHER"
        out.append({"claim_id": c.claim_id, "verdict": c.verdict, "label": label,
                    "lane": c.lane, "case_id": c.id})
    return out
