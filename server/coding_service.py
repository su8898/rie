"""Coding intelligence (SPECIFICATION §6) — tariff / NAPPI aggregation, tier-aware overage vs
reference, condition cost bands per injury (intensity-split), and negotiation targets.

Read-only analytics over the persisted, adjudicated corpus. `billing_lines` already carry the
resolved reference / payable / legal status, so nothing is re-priced here; condition bands read
the per-claim medical total (Determination) keyed by injury class (ICD-10 3-char) from the claim.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models

DRIFT_MIN_MONTHS = 6                                   # history needed before a trend is judged
DRIFT_MIN_LINES = 5                                    # months thinner than this are ignored (noise)
_PAYMENT_RULE = ("ENFORCEABLE", "ACCEPTED")            # references that are a real price, not a signal

MIN_ROBUST = 20                                        # domain-logic §6 — small-n guard on cost bands
_CONSERVATIVE_DISCIPLINES = {"", "GP"}                 # any other discipline => specialist-involved


# ── tariff / NAPPI aggregation + tier-aware overage ───────────────────────────
def _line_over(r) -> tuple[float, float, float]:
    """(captured, signal, uncovered_billed) for one adjudicated line."""
    if r.reference is None:
        return 0.0, 0.0, r.billed                       # no reference -> negotiate to establish one
    if r.billed > r.payable:                            # repriced to an enforceable/accepted ref
        return r.billed - r.payable, 0.0, 0.0           # already captured (pay-min)
    if r.legal_status in ("INTERDICTED", "ENDOGENOUS") and r.billed > r.reference:
        return 0.0, r.billed - r.reference, 0.0         # signal only -> negotiation target
    return 0.0, 0.0, 0.0


def code_aggregation(db: Session, kind: Optional[str] = None, limit: int = 200) -> list[dict]:
    agg: dict = defaultdict(lambda: {
        "n_lines": 0, "claims": set(), "providers": set(), "billed": 0.0, "payable": 0.0,
        "captured": 0.0, "signal": 0.0, "uncovered": 0.0, "uncovered_lines": 0,
        "src": Counter(), "status": Counter()})
    stmt = select(models.BillingLineRecord)
    if kind:
        stmt = stmt.where(models.BillingLineRecord.kind == kind)
    for r in db.scalars(stmt):
        a = agg[(r.kind, r.code)]
        a["n_lines"] += 1
        a["claims"].add(r.claim_id)
        a["providers"].add(r.provider_id)
        a["billed"] += r.billed
        a["payable"] += r.payable
        cap, sig, unc = _line_over(r)
        a["captured"] += cap
        a["signal"] += sig
        a["uncovered"] += unc
        a["uncovered_lines"] += int(unc > 0)
        a["src"][r.src] += 1
        a["status"][r.legal_status or "—"] += 1
    rows = [{
        "kind": kind_, "code": code, "n_lines": a["n_lines"], "n_claims": len(a["claims"]),
        "n_providers": len(a["providers"]), "billed": round(a["billed"], 2),
        "payable": round(a["payable"], 2), "repricing_captured": round(a["captured"], 2),
        "over_reference_signal": round(a["signal"], 2), "uncovered_billed": round(a["uncovered"], 2),
        "uncovered_lines": a["uncovered_lines"],
        "top_src": a["src"].most_common(1)[0][0] if a["src"] else None,
        "legal_status": a["status"].most_common(1)[0][0] if a["status"] else None,
    } for (kind_, code), a in agg.items()]
    rows.sort(key=lambda x: -x["billed"])
    return rows[:limit]


def negotiation_targets(db: Session, limit: int = 50) -> list[dict]:
    """Codes where negotiating an ENFORCEABLE rate would capture uncontrolled spend: the
    over-reference *signal* (paid in full against an interdicted/endogenous ref) plus uncovered
    billing. Already-negotiated codes are excluded."""
    negotiated = {(r.kind, r.code) for r in db.scalars(select(models.RefNegotiated))}
    out = []
    for r in code_aggregation(db, limit=10_000):
        if (r["kind"], r["code"]) in negotiated:
            continue
        potential = round(r["over_reference_signal"] + r["uncovered_billed"], 2)
        if potential > 0:
            out.append({**r, "potential_saving": potential})
    out.sort(key=lambda x: -x["potential_saving"])
    return out[:limit]


# ── condition cost bands (per injury class, intensity-split) ──────────────────
def _pctl(s: list[float], q: float) -> float:
    if not s:
        return 0.0
    if len(s) == 1:
        return s[0]
    pos = q * (len(s) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (pos - lo) * (s[hi] - s[lo])


def _bands(totals: list[float]) -> dict:
    s = sorted(totals)
    return {"p25": round(_pctl(s, 0.25), 2), "p50": round(_pctl(s, 0.50), 2),
            "p75": round(_pctl(s, 0.75), 2), "p90": round(_pctl(s, 0.90), 2),
            "min": round(s[0], 2), "max": round(s[-1], 2)}


def _injury_and_intensity(raw: dict) -> tuple[str, str]:
    lines = raw.get("lines", []) if isinstance(raw, dict) else []
    dx = next((str(l["dx"])[:3] for l in lines if l.get("dx")), "")
    specialist = any((l.get("discipline") or "").upper() not in _CONSERVATIVE_DISCIPLINES
                     for l in lines)
    return dx, ("SPECIALIST" if specialist else "CONSERVATIVE")


def _condition_totals(db: Session):
    """injury_class -> combined [per-claim medical totals], and injury -> intensity -> [totals]."""
    dets = {d.claim_id: d.medical_payable for d in db.scalars(select(models.Determination))}
    combined: dict = defaultdict(list)
    by_intensity: dict = defaultdict(lambda: defaultdict(list))
    for c in db.scalars(select(models.ClaimRecord)):
        if c.claim_id not in dets:
            continue
        dx, intensity = _injury_and_intensity(c.raw or {})
        if not dx:
            continue
        combined[dx].append(dets[c.claim_id])
        by_intensity[dx][intensity].append(dets[c.claim_id])
    return combined, by_intensity


def condition_bands(db: Session, min_robust: int = MIN_ROBUST) -> list[dict]:
    combined, by_intensity = _condition_totals(db)
    out = []
    for injury, totals in sorted(combined.items(), key=lambda kv: -len(kv[1])):
        out.append({
            "injury_class": injury, "n": len(totals), "robust": len(totals) >= min_robust,
            "bands": _bands(totals) if len(totals) >= min_robust else None,
            "by_intensity": {intensity: {"n": len(v), "robust": len(v) >= min_robust,
                                         "bands": _bands(v) if len(v) >= min_robust else None}
                             for intensity, v in by_intensity[injury].items()},
        })
    return out


def estimate(db: Session, injury_class: str, amount: float, min_robust: int = MIN_ROBUST) -> dict:
    combined, _ = _condition_totals(db)
    totals = combined.get(injury_class, [])
    if len(totals) < min_robust:
        return {"injury_class": injury_class, "n": len(totals), "robust": False,
                "classification": "UNKNOWN", "amount": amount}
    b = _bands(totals)
    cls = ("BELOW_TYPICAL" if amount < b["p25"] else "TYPICAL" if amount <= b["p75"]
           else "HIGH" if amount <= b["p90"] else "OUTLIER")
    return {"injury_class": injury_class, "n": len(totals), "robust": True,
            "classification": cls, "amount": amount, "bands": b}


# ── price drift — the slow ratchet a cross-sectional outlier screen misses ─────
def _ols_slope(points: list[tuple[float, float]]) -> Optional[float]:
    """Least-squares slope of y over x; None when it cannot be fitted."""
    n = len(points)
    sx, sy = sum(p[0] for p in points), sum(p[1] for p in points)
    denom = n * sum(p[0] * p[0] for p in points) - sx * sx
    if n < 2 or denom == 0:
        return None
    return (n * sum(p[0] * p[1] for p in points) - sx * sy) / denom


def price_drift(db: Session, min_months: int = DRIFT_MIN_MONTHS,
                min_lines: int = DRIFT_MIN_LINES, limit: int = 40) -> dict:
    """Per provider per service month: billed ÷ reference over the lines with an enforceable or
    accepted reference, and the least-squares slope of that ratio over time (ported from CIE's
    drift monitor). The reference on each stored line is the one in force on its service date, so
    a tariff increase does not read as drift. The output is a worklist, never a verdict."""
    billed: dict = defaultdict(float)
    ref: dict = defaultdict(float)
    n_lines: Counter = Counter()
    L = models.BillingLineRecord
    for r in db.scalars(select(L).where(L.reference.is_not(None), L.reference > 0,
                                        L.service_date.is_not(None), L.provider_id != "",
                                        L.legal_status.in_(_PAYMENT_RULE))):
        key = (r.provider_id, f"{r.service_date:%Y-%m}")
        billed[key] += r.billed
        ref[key] += r.reference
        n_lines[key] += 1
    series: dict = defaultdict(list)
    for (pid, month), b in billed.items():
        if n_lines[(pid, month)] >= min_lines:
            series[pid].append((month, b / ref[(pid, month)], n_lines[(pid, month)]))
    rows = []
    for pid, months in series.items():
        months.sort()
        slope = _ols_slope([(float(i), ratio) for i, (_m, ratio, _n) in enumerate(months)])
        if len(months) < min_months or slope is None:
            continue
        rows.append({
            "provider_id": pid, "n_months": len(months),
            "first_month": months[0][0], "last_month": months[-1][0],
            "first_ratio": round(months[0][1], 3), "last_ratio": round(months[-1][1], 3),
            "slope_per_month": round(slope, 4),
            "series": [{"month": m, "ratio": round(x, 3), "lines": n} for m, x, n in months],
        })
    rows.sort(key=lambda x: x["slope_per_month"], reverse=True)
    return {"min_months": min_months, "min_lines": min_lines, "n_providers": len(rows),
            "rising": [x for x in rows if x["slope_per_month"] > 0][:limit]}
