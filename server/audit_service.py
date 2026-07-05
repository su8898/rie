"""Post-payment audit / clawback recovery (domain-logic §8e).

Machine OPEN -> UNDER_REVIEW -> RECOVERED / CLEARED. The recovery sweep is the Lane-3 recovery
half: it scans *paid* claims and opens a clawback item where the claim was banded RED / disposed
FRAUD, or — the realistic "provider found dirty after the fact" case — where a provider on the
claim now carries a party-intelligence risk score at/above the threshold. Realised recovery is
captured on RECOVERED; ROI rolls up at-stake vs recovered.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models, statemachine as sm
from .party_intel_service import providers as provider_intel

AUDIT = sm.Machine(
    name="audit", state_attr="status", initial="OPEN",
    terminal=frozenset({"RECOVERED", "CLEARED"}),
    transitions=(
        sm.T("OPEN", "review", "UNDER_REVIEW", ("INVESTIGATOR",)),
        sm.T("OPEN", "clear", "CLEARED", ("INVESTIGATOR",)),
        sm.T("UNDER_REVIEW", "recover", "RECOVERED", ("INVESTIGATOR",)),
        sm.T("UNDER_REVIEW", "clear", "CLEARED", ("INVESTIGATOR",)),
    ),
)

_RECOVERY_OUTCOMES = {"RECOVERED_FULL", "RECOVERED_PARTIAL", "WRITTEN_OFF", "NOT_PURSUED"}


def _paid_by_claim(db: Session) -> dict:
    paid: dict = defaultdict(float)
    for inst in db.scalars(select(models.PaymentInstruction).where(
            models.PaymentInstruction.paid.is_(True))):
        paid[inst.claim_id] += inst.amount
    return paid


def recovery_sweep(db: Session, user: dict, threshold: float = 20.0) -> list[int]:
    prov_scores = {p["provider_id"]: p["score"] for p in provider_intel(db)}
    paid = _paid_by_claim(db)
    existing = {a.claim_id for a in db.scalars(select(models.AuditQueue))}   # idempotent
    dets = {d.claim_id: d for d in
            db.scalars(select(models.Determination).order_by(models.Determination.id))}

    opened = []
    for claim_id, amount in paid.items():
        if claim_id in existing:
            continue
        provs = set(db.scalars(select(models.BillingLineRecord.provider_id)
                               .where(models.BillingLineRecord.claim_id == claim_id)))
        hi = sorted((p for p in provs if prov_scores.get(p, 0.0) >= threshold),
                    key=lambda p: prov_scores.get(p, 0.0), reverse=True)
        det = dets.get(claim_id)
        red_fraud = det is not None and (det.band == "RED" or det.disposition == "FRAUD")
        if hi:
            reason = f"high-risk provider {hi[0]} (score {prov_scores[hi[0]]})"
        elif red_fraud:
            reason = f"{det.band}/{det.disposition} determination, paid"
        else:
            continue
        a = models.AuditQueue(claim_id=claim_id, status="OPEN", reason=reason,
                              amount_at_stake=round(amount, 2), amount_recovered=0.0,
                              opened_by=user["username"])
        db.add(a)
        db.flush()
        opened.append(a.id)
    db.commit()
    return opened


def transition(db: Session, audit_id: int, action: str, user: dict,
               amount: Optional[float] = None, outcome: Optional[str] = None
               ) -> "models.AuditQueue":
    a = db.get(models.AuditQueue, audit_id)
    if a is None:
        raise sm.IllegalTransition("no such audit item")
    if action == "recover" and outcome is not None and outcome not in _RECOVERY_OUTCOMES:
        raise sm.GateNotMet(f"invalid recovery outcome: {outcome}")
    sm.fire(db, AUDIT, a, audit_id, action, user, detail={"amount": amount, "outcome": outcome})
    if action == "review":
        a.assigned_to = user["username"]
    elif action == "recover":
        a.amount_recovered = float(amount) if amount is not None else a.amount_at_stake
        a.recovery_outcome = outcome or ("RECOVERED_FULL" if a.amount_recovered >= a.amount_at_stake
                                         else "RECOVERED_PARTIAL")
    elif action == "clear":
        a.recovery_outcome = "CLEARED"
    db.commit()
    return a


def roi(db: Session) -> dict:
    items = list(db.scalars(select(models.AuditQueue)))
    at_stake = sum(a.amount_at_stake for a in items)
    recovered = sum(a.amount_recovered for a in items)
    return {
        "n_items": len(items),
        "amount_at_stake": round(at_stake, 2),
        "amount_recovered": round(recovered, 2),
        "recovery_rate": round(100.0 * recovered / at_stake, 1) if at_stake else 0.0,
        "by_status": dict(Counter(a.status for a in items)),
        "by_outcome": dict(Counter(a.recovery_outcome for a in items if a.recovery_outcome)),
    }


def item_dict(a: "models.AuditQueue") -> dict:
    return {"id": a.id, "claim_id": a.claim_id, "status": a.status, "reason": a.reason,
            "amount_at_stake": a.amount_at_stake, "amount_recovered": a.amount_recovered,
            "recovery_outcome": a.recovery_outcome, "assigned_to": a.assigned_to,
            "opened_by": a.opened_by, "actions": AUDIT.actions_from(a.status),
            "opened_at": a.opened_at.isoformat() if a.opened_at else None}
