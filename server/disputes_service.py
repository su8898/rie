"""Objection / dispute register — the CIE s91-objection pattern generalised (SPECIFICATION §6).

One register for every objection to a determination, split across the three RAF paths: INTERNAL
reconsideration, the HPCSA tribunal (serious injury), and the litigation hand-off. Machine
LODGED -> UNDER_RECONSIDERATION -> UPHELD / REJECTED -> REFERRED -> RESOLVED (or WITHDRAWN), on the
shared state-machine primitive (illegal -> 409, wrong-actor -> 403, gate -> 409, actor-stamped log).
Referral picks the channel by subject (SERIOUS_INJURY -> HPCSA tribunal, else litigation) and, for
a litigation hand-off, opens a Litigation record and links it.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .clock import utcnow
from . import models, statemachine as sm

SUBJECTS = {"MERITS", "QUANTUM", "TARIFF", "REPUDIATION", "SERIOUS_INJURY"}
RAISERS = {"CLAIMANT", "PROVIDER", "ATTORNEY"}
CHANNELS = {"INTERNAL", "HPCSA_TRIBUNAL", "LITIGATION"}
OBJECTION_WINDOW_DAYS = 180                             # the s91 / W.G.29 180-day analogue

DISPUTE = sm.Machine(
    name="dispute", state_attr="status", initial="LODGED",
    terminal=frozenset({"UPHELD", "WITHDRAWN", "RESOLVED"}),
    transitions=(
        sm.T("LODGED", "reconsider", "UNDER_RECONSIDERATION", ("HANDLER", "MEDICAL_OFFICER", "LEGAL")),
        sm.T("LODGED", "refer", "REFERRED", ("LEGAL",)),          # e.g. SI rejection straight to HPCSA
        sm.T("LODGED", "withdraw", "WITHDRAWN"),
        sm.T("UNDER_RECONSIDERATION", "uphold", "UPHELD", ("HANDLER", "MEDICAL_OFFICER", "LEGAL")),
        sm.T("UNDER_RECONSIDERATION", "reject", "REJECTED", ("HANDLER", "MEDICAL_OFFICER", "LEGAL")),
        sm.T("UNDER_RECONSIDERATION", "withdraw", "WITHDRAWN"),
        sm.T("REJECTED", "refer", "REFERRED", ("LEGAL",)),        # escalate after an internal rejection
        sm.T("REFERRED", "resolve", "RESOLVED", ("LEGAL",)),      # external (tribunal / court) outcome
    ),
)


def lodge(db: Session, user: dict, claim_id: str, subject: str, raised_by: str,
          grounds: str = "") -> "models.Dispute":
    if subject not in SUBJECTS:
        raise sm.GateNotMet(f"unknown dispute subject: {subject}")
    if raised_by not in RAISERS:
        raise sm.GateNotMet(f"unknown raised_by: {raised_by}")
    d = models.Dispute(
        claim_id=claim_id, subject=subject, raised_by=raised_by, grounds=grounds, status="LODGED",
        opened_by=user["username"], deadline=utcnow() + timedelta(days=OBJECTION_WINDOW_DAYS))
    db.add(d)
    db.commit()
    return d


def transition(db: Session, dispute_id: int, action: str, user: dict, outcome: Optional[str] = None,
               channel: Optional[str] = None, linked_ref: Optional[str] = None) -> "models.Dispute":
    d = db.get(models.Dispute, dispute_id)
    if d is None:
        raise sm.IllegalTransition("no such dispute")
    if channel is not None and channel not in CHANNELS:
        raise sm.GateNotMet(f"unknown channel: {channel}")
    sm.fire(db, DISPUTE, d, dispute_id, action, user,
            detail={"outcome": outcome, "channel": channel})
    if action == "reconsider":
        d.channel = "INTERNAL"
    elif action == "refer":
        d.channel = channel or ("HPCSA_TRIBUNAL" if d.subject == "SERIOUS_INJURY" else "LITIGATION")
        if d.channel == "LITIGATION" and linked_ref is None:      # the litigation hand-off
            lit = models.Litigation(claim_id=d.claim_id, status="SUMMONS_SERVED",
                                    default_judgment=False)
            db.add(lit)
            db.flush()
            d.linked_ref = f"litigation:{lit.id}"
        else:
            d.linked_ref = linked_ref
    elif action == "uphold":
        d.outcome, d.closed_at = outcome, utcnow()          # decision revised in the disputant's favour
    elif action == "reject":
        d.outcome = outcome                                       # decision stands (may still be referred)
    elif action == "resolve":
        d.outcome, d.closed_at = outcome, utcnow()
    elif action == "withdraw":
        d.closed_at = utcnow()
    db.commit()
    return d


def _days_left(d: "models.Dispute", now: datetime) -> Optional[int]:
    return (d.deadline - now).days if d.deadline is not None else None


def item_dict(d: "models.Dispute", now: Optional[datetime] = None) -> dict:
    now = now or utcnow()
    return {
        "id": d.id, "claim_id": d.claim_id, "subject": d.subject, "raised_by": d.raised_by,
        "grounds": d.grounds, "status": d.status, "channel": d.channel, "outcome": d.outcome,
        "linked_ref": d.linked_ref, "opened_by": d.opened_by,
        "opened_at": d.opened_at.isoformat() if d.opened_at else None,
        "deadline": d.deadline.isoformat() if d.deadline else None,
        "days_to_deadline": _days_left(d, now),
        "overdue": bool(d.status not in DISPUTE.terminal and d.deadline is not None and d.deadline < now),
        "closed_at": d.closed_at.isoformat() if d.closed_at else None,
        "actions": DISPUTE.actions_from(d.status),
    }


def analytics(db: Session) -> dict:
    items = list(db.scalars(select(models.Dispute)))
    open_items = [d for d in items if d.status not in DISPUTE.terminal]
    return {
        "n": len(items), "open": len(open_items),
        "by_subject": dict(Counter(d.subject for d in items)),
        "by_status": dict(Counter(d.status for d in items)),
        "by_channel": dict(Counter(d.channel for d in items if d.channel)),
        "by_raised_by": dict(Counter(d.raised_by for d in items)),
    }
