"""Party intelligence & cohorting (domain-logic §7).

Aggregates the corpus into per-party statistics, assigns each provider a data-derived archetype
(its cohort), computes WITHIN-COHORT value percentiles (the false-positive control), and scores
each party via the pure `party_scoring` core. Also: attorney cohorting, claimant recurrence over
the accident graph, a disparate-impact fairness report, and a risk sweep.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from statistics import mean

from sqlalchemy import select
from sqlalchemy.orm import Session

import engine

from . import models
from .party_scoring import PartyStats, party_risk, percentile

_FRAUD = engine.Category.FRAUD
_SPECIALIST_VALUE = 800.0
_MATERIALS_SHARE = 0.6


def _nonpricing_fraud(reasons) -> bool:
    """A fraud-category reason (pricing/duplicates are ADJUSTED, so excluded by construction)."""
    return any(r in engine.R and engine.R[r].category is _FRAUD for r in (reasons or []))


def _latest_dets(db: Session) -> dict:
    out = {}
    for d in db.scalars(select(models.Determination).order_by(models.Determination.id)):
        out[d.claim_id] = d                          # ascending id -> latest wins
    return out


def _archetype(nappi_share: float, avg_value: float) -> str:
    if nappi_share >= _MATERIALS_SHARE:
        return "MATERIALS"
    if avg_value >= _SPECIALIST_VALUE:
        return "SPECIALIST"
    return "GENERAL"


def _band_stats(ds) -> tuple[int, int, float, int]:
    n = len(ds)
    red = sum(1 for d in ds if d.band == "RED")
    amber = sum(1 for d in ds if d.band == "AMBER")
    avg_score = mean([d.score for d in ds]) if ds else 0.0
    flagged = sum(1 for d in ds if _nonpricing_fraud(d.reasons))
    return red, amber, avg_score, flagged


def providers(db: Session) -> list[dict]:
    dets = _latest_dets(db)
    agg: dict = defaultdict(lambda: {"claims": set(), "lines": 0, "nappi": 0, "billed": 0.0})
    for line in db.scalars(select(models.BillingLineRecord)):
        p = agg[line.provider_id or "—"]
        p["claims"].add(line.claim_id)
        p["lines"] += 1
        p["billed"] += line.billed
        if line.kind == "NAPPI":
            p["nappi"] += 1

    for p in agg.values():
        p["avg_value"] = round(p["billed"] / p["lines"], 2) if p["lines"] else 0.0
        p["nappi_share"] = p["nappi"] / p["lines"] if p["lines"] else 0.0
        p["archetype"] = _archetype(p["nappi_share"], p["avg_value"])

    cohort_values: dict = defaultdict(list)
    for p in agg.values():
        cohort_values[p["archetype"]].append(p["avg_value"])

    out = []
    for pid, p in agg.items():
        ds = [dets[c] for c in p["claims"] if c in dets]
        n = len(ds)
        red, amber, avg_score, flagged = _band_stats(ds)
        stats = PartyStats(
            n_claims=n,
            red_rate=100.0 * red / n if n else 0.0,
            amber_rate=100.0 * amber / n if n else 0.0,
            avg_score=avg_score,
            util_rate=100.0 * flagged / n if n else 0.0,
            value_p=percentile(cohort_values[p["archetype"]], p["avg_value"]),
        )
        out.append({
            "provider_id": pid, "archetype": p["archetype"], "cohort": p["archetype"],
            "n_claims": n, "n_lines": p["lines"], "billed": round(p["billed"], 2),
            "avg_value": p["avg_value"], "value_percentile": stats.value_p,
            "red_rate": round(stats.red_rate, 1), "flag_rate": round(stats.util_rate, 1),
            **party_risk(stats),
        })
    out.sort(key=lambda r: r["score"], reverse=True)
    return out


def attorneys(db: Session) -> list[dict]:
    dets = _latest_dets(db)
    agg: dict = defaultdict(lambda: {"claims": [], "types": Counter(), "late": 0})
    for c in db.scalars(select(models.ClaimRecord)):
        att = (c.raw or {}).get("attorney")
        if not att:
            continue
        a = agg[att]
        a["claims"].append(c)
        a["types"][c.claim_type] += 1
        if (c.lodged_on - c.accident_date).days > int(365 * 2.5):   # near-prescription lodgement
            a["late"] += 1

    volumes = [len(a["claims"]) for a in agg.values()]
    out = []
    for att, a in agg.items():
        ds = [dets[c.claim_id] for c in a["claims"] if c.claim_id in dets]
        n = len(a["claims"])
        red, amber, avg_score, flagged = _band_stats(ds)
        cohort = "HIGH_VOLUME" if n >= 10 else "BOUTIQUE" if n >= 3 else "GENERAL"
        stats = PartyStats(
            n_claims=n,
            red_rate=100.0 * red / len(ds) if ds else 0.0,
            amber_rate=100.0 * amber / len(ds) if ds else 0.0,
            avg_score=avg_score,
            util_rate=100.0 * flagged / len(ds) if ds else 0.0,
            value_p=percentile(volumes, n),           # cohort-outlier proxy: volume percentile
        )
        out.append({
            "attorney": att, "cohort": cohort, "n_claims": n,
            "claim_type_mix": dict(a["types"]),
            "late_lodgement_share": round(100.0 * a["late"] / n, 1) if n else 0.0,
            **party_risk(stats),
        })
    out.sort(key=lambda r: r["score"], reverse=True)
    return out


def claimants(db: Session) -> list[dict]:
    """Recurrence only (§7): a claimant token appearing across >= 2 accidents."""
    rec: dict = defaultdict(set)
    for acc in db.scalars(select(models.AccidentRecord)):
        for token in (acc.parties or []):
            rec[token].add(acc.accident_id)
    out = [{"party_token": t, "n_accidents": len(a), "accidents": sorted(a)}
           for t, a in rec.items() if len(a) >= 2]
    out.sort(key=lambda r: r["n_accidents"], reverse=True)
    return out


IMPACT_LOW = 0.80          # cohort rate < 0.8x overall -> under-scrutiny tail (review)
IMPACT_HIGH = 1.25         # cohort rate > 1.25x overall -> over-scrutiny tail (review)
MIN_GROUP = 5              # too few claims in a cohort to judge its impact


def fairness(db: Session) -> dict:
    """Disparate-impact by provider cohort. Reports each cohort's flag rate, its **impact ratio**
    (cohort rate / overall rate) and — for cohorts with enough claims whose impact falls outside
    [IMPACT_LOW, IMPACT_HIGH] on *either* tail — a review flag (over-scrutiny AND under-scrutiny
    both warrant a look). Also the classic four-fifths ratio (min/max) as a headline gauge."""
    by_cohort: dict = defaultdict(lambda: {"n": 0, "flagged": 0.0})
    for p in providers(db):
        c = by_cohort[p["cohort"]]
        c["n"] += p["n_claims"]
        c["flagged"] += p["flag_rate"] * p["n_claims"] / 100.0
    total_n = sum(v["n"] for v in by_cohort.values())
    total_flagged = sum(v["flagged"] for v in by_cohort.values())
    overall = round(100.0 * total_flagged / total_n, 1) if total_n else 0.0
    rows = []
    for k, v in by_cohort.items():
        rate = round(100.0 * v["flagged"] / v["n"], 1) if v["n"] else 0.0
        small = v["n"] < MIN_GROUP
        impact = round(rate / overall, 2) if overall > 0 else None
        review = bool(not small and impact is not None
                      and (impact < IMPACT_LOW or impact > IMPACT_HIGH))
        rows.append({"cohort": k, "n_claims": v["n"], "flag_rate": rate,
                     "impact": impact, "small": small, "review": review})
    rows.sort(key=lambda r: r["cohort"])
    rates = [r["flag_rate"] for r in rows if r["n_claims"] > 0]
    hi = max(rates) if rates else 0.0
    ratio = round(min(rates) / hi, 2) if rates and hi > 0 else 1.0
    return {"by_cohort": rows, "overall_flag_rate": overall,
            "four_fifths_ratio": ratio, "pass": ratio >= 0.8,
            "impact_low": IMPACT_LOW, "impact_high": IMPACT_HIGH, "min_group": MIN_GROUP}


def risk_sweep(db: Session, threshold: float = 55.0) -> dict:
    flagged = ([{"type": "provider", "id": p["provider_id"], **p} for p in providers(db)
                if p["score"] >= threshold]
               + [{"type": "attorney", "id": a["attorney"], **a} for a in attorneys(db)
                  if a["score"] >= threshold])
    flagged.sort(key=lambda r: r["score"], reverse=True)
    return {"threshold": threshold, "n": len(flagged), "flagged": flagged}
