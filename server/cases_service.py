"""Investigation / review cases — the CIE case machine (domain-logic §8e).

Lanes route work: REVIEW -> HANDLER, BLOCK / CLAWBACK -> INVESTIGATOR; escalation moves a case to
the INVESTIGATOR pool. Priority sets the SLA clock ({1:1, 2:3, 3:7, 4:10, 5:14} days). Closing a
case captures the outcome (verdict, root cause, rand recovered / prevented) — the ground-truth
label that feeds engine precision / recall. Machine OPEN -> IN_REVIEW / ESCALATED -> CLOSED, on the
shared state-machine primitive (illegal -> 409, wrong-actor -> 403, gate -> 409, actor-stamped log).
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models, statemachine as sm

LANE_OWNER = {"REVIEW": "HANDLER", "BLOCK": "INVESTIGATOR", "CLAWBACK": "INVESTIGATOR"}
SLA_DAYS = {1: 1, 2: 3, 3: 7, 4: 10, 5: 14}
VERDICTS = {"CONFIRMED_FRAUD", "CLEARED", "ADJUSTED", "NO_ACTION", "REFERRED_LEGAL"}

CASE = sm.Machine(
    name="case", state_attr="status", initial="OPEN", terminal=frozenset({"CLOSED"}),
    transitions=(
        sm.T("OPEN", "assign", "IN_REVIEW", ("HANDLER", "INVESTIGATOR")),
        sm.T("OPEN", "escalate", "ESCALATED", ("HANDLER", "INVESTIGATOR")),
        sm.T("OPEN", "close", "CLOSED", ("HANDLER", "INVESTIGATOR")),
        sm.T("IN_REVIEW", "escalate", "ESCALATED", ("HANDLER", "INVESTIGATOR")),
        sm.T("IN_REVIEW", "close", "CLOSED", ("HANDLER", "INVESTIGATOR")),
        sm.T("ESCALATED", "close", "CLOSED", ("INVESTIGATOR",)),   # escalated cases close by INVESTIGATOR
    ),
)


def open_case(db: Session, user: dict, lane: str, reason: str, claim_id: Optional[str] = None,
              priority: int = 3, rand_at_stake: float = 0.0) -> "models.Case":
    if lane not in LANE_OWNER:
        raise sm.GateNotMet(f"unknown lane: {lane} (REVIEW | BLOCK | CLAWBACK)")
    if int(priority) not in SLA_DAYS:
        raise sm.GateNotMet("priority must be 1..5")
    c = models.Case(
        claim_id=claim_id, lane=lane, status="OPEN", priority=int(priority), reason=reason,
        rand_at_stake=round(float(rand_at_stake or 0.0), 2), opened_by=user["username"],
        due_at=datetime.now() + timedelta(days=SLA_DAYS[int(priority)]))
    db.add(c)
    db.commit()
    return c


def _lane_gate(case: "models.Case", user: dict):
    def gate() -> None:
        owner = LANE_OWNER.get(case.lane)
        if user.get("role") != "ADMIN" and owner and user.get("role") != owner:
            raise sm.GateNotMet(f"{case.lane} lane is owned by {owner}, not {user.get('role')}")
    return gate


def transition(db: Session, case_id: int, action: str, user: dict, verdict: Optional[str] = None,
               root_cause: Optional[str] = None, recovered: Optional[float] = None,
               prevented: Optional[float] = None) -> "models.Case":
    c = db.get(models.Case, case_id)
    if c is None:
        raise sm.IllegalTransition("no such case")
    if action == "close" and verdict is not None and verdict not in VERDICTS:
        raise sm.GateNotMet(f"invalid verdict: {verdict}")
    # lane ownership is enforced while the case sits in its lane; once ESCALATED the INVESTIGATOR
    # transition role governs, so the lane gate is dropped.
    gate = _lane_gate(c, user) if c.status != "ESCALATED" else None
    sm.fire(db, CASE, c, case_id, action, user, gate=gate,
            detail={"verdict": verdict, "root_cause": root_cause})
    if action == "assign":
        c.assigned_to = user["username"]
    elif action == "escalate":
        c.assigned_to = None                              # back to the INVESTIGATOR pool
    elif action == "close":
        c.verdict, c.root_cause = verdict, root_cause
        c.rand_recovered = round(float(recovered or 0.0), 2)
        c.rand_prevented = round(float(prevented or 0.0), 2)
        c.closed_at = datetime.now()
    db.commit()
    return c


def add_note(db: Session, case_id: int, user: dict, body: str) -> "models.CaseNote":
    if db.get(models.Case, case_id) is None:
        raise sm.IllegalTransition("no such case")
    n = models.CaseNote(case_id=case_id, author=user["username"], body=body)
    db.add(n)
    db.commit()
    return n


def notes(db: Session, case_id: int) -> list[dict]:
    return [{"id": n.id, "author": n.author, "body": n.body,
             "created_at": n.created_at.isoformat() if n.created_at else None}
            for n in db.scalars(select(models.CaseNote).where(models.CaseNote.case_id == case_id)
                                .order_by(models.CaseNote.id))]


def _overdue(c: "models.Case", now: datetime) -> bool:
    return bool(c.status != "CLOSED" and c.due_at is not None and c.due_at < now)


def item_dict(c: "models.Case", now: Optional[datetime] = None) -> dict:
    now = now or datetime.now()
    return {
        "id": c.id, "claim_id": c.claim_id, "lane": c.lane, "status": c.status,
        "priority": c.priority, "reason": c.reason, "rand_at_stake": c.rand_at_stake,
        "owner_role": LANE_OWNER.get(c.lane), "assigned_to": c.assigned_to,
        "verdict": c.verdict, "root_cause": c.root_cause,
        "rand_recovered": c.rand_recovered, "rand_prevented": c.rand_prevented,
        "opened_by": c.opened_by,
        "opened_at": c.opened_at.isoformat() if c.opened_at else None,
        "due_at": c.due_at.isoformat() if c.due_at else None,
        "closed_at": c.closed_at.isoformat() if c.closed_at else None,
        "sla_days": SLA_DAYS.get(c.priority),
        "days_to_sla": (c.due_at - now).days if c.due_at is not None else None,
        "overdue": _overdue(c, now), "actions": CASE.actions_from(c.status),
    }


def analytics(db: Session) -> dict:
    items = list(db.scalars(select(models.Case)))
    now = datetime.now()
    open_items = [c for c in items if c.status != "CLOSED"]
    return {
        "n": len(items), "open": len(open_items),
        "by_lane": dict(Counter(c.lane for c in items)),
        "by_status": dict(Counter(c.status for c in items)),
        "by_verdict": dict(Counter(c.verdict for c in items if c.verdict)),
        "rand_at_stake_open": round(sum(c.rand_at_stake for c in open_items), 2),
        "rand_recovered": round(sum(c.rand_recovered for c in items), 2),
        "rand_prevented": round(sum(c.rand_prevented for c in items), 2),
        "overdue": sum(1 for c in open_items if _overdue(c, now)),
    }


def labels(db: Session) -> list[dict]:
    """Ground-truth labels from closed cases — the raw material for engine precision / recall."""
    return [{"case_id": c.id, "claim_id": c.claim_id, "lane": c.lane, "verdict": c.verdict,
             "root_cause": c.root_cause}
            for c in db.scalars(select(models.Case).where(models.Case.status == "CLOSED")
                                .order_by(models.Case.id)) if c.verdict]
