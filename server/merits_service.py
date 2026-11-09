"""Merits determination state machine (domain-logic §4c, §8).

PENDING → ACCEPTED(fault %) / REJECTED(s19 ground); a rejection is appealable
(REJECTED → APPEALED → ACCEPTED / REJECTED). Merits acceptance is the payment gate — the
lifecycle's QUANTUM transition and the offer builder both read this.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models, statemachine as sm
from .validation import MERITS_GROUNDS

MERITS = sm.Machine(
    name="merits", state_attr="status", initial="PENDING",
    transitions=(
        sm.T("PENDING", "accept", "ACCEPTED", ("HANDLER", "LEGAL")),
        sm.T("PENDING", "reject", "REJECTED", ("HANDLER", "LEGAL")),
        sm.T("REJECTED", "appeal", "APPEALED", ("LEGAL",)),
        sm.T("APPEALED", "accept", "ACCEPTED", ("LEGAL",)),
        sm.T("APPEALED", "dismiss", "REJECTED", ("LEGAL",)),
    ),
)

_REJECT_ACTIONS = {"reject", "dismiss"}


def get_or_create(db: Session, claim_id: str) -> "models.MeritsDetermination":
    m = db.get(models.MeritsDetermination, claim_id)
    if m is None:
        m = models.MeritsDetermination(claim_id=claim_id, status="PENDING")
        db.add(m)
        db.flush()
    return m


def decide(db: Session, claim_id: str, action: str, user: dict,
           fault_pct: Optional[float] = None, ground: Optional[str] = None
           ) -> "models.MeritsDetermination":
    if action == "accept" and fault_pct is not None:
        fault_pct = float(fault_pct)
        if not (0.0 <= fault_pct <= 100.0):
            raise sm.GateNotMet(f"fault_pct must be within 0..100, got {fault_pct}")
    if action in _REJECT_ACTIONS and ground is not None and ground not in MERITS_GROUNDS:
        raise sm.GateNotMet(f"ground must be one of {sorted(MERITS_GROUNDS)}")
    m = get_or_create(db, claim_id)
    sm.fire(db, MERITS, m, claim_id, action, user, detail={"fault_pct": fault_pct, "ground": ground})
    if action == "accept":
        m.fault_pct = float(fault_pct) if fault_pct is not None else 0.0
        m.ground = None
    elif action in _REJECT_ACTIONS:
        m.ground = ground or "S19_EXCLUSION"
    db.commit()
    return m


def history(db: Session, claim_id: str) -> list:
    return list(db.scalars(
        select(models.TransitionLog)
        .where(models.TransitionLog.entity_type == "merits",
               models.TransitionLog.entity_id == str(claim_id))
        .order_by(models.TransitionLog.id)))
