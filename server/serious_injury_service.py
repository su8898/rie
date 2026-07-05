"""Serious-injury (RAF 4) state machine (domain-logic §8b).

A serious-injury assessment (RAF 4) is SUBMITTED, then a medical officer either RAF_ACCEPTS or
RAF_REJECTS it; a rejection is appealable to the HPCSA (RAF_REJECTED → HPCSA_APPEAL), which is
then UPHELD or DISMISSED by legal. Acceptance is the gate for general damages.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models, statemachine as sm

SI = sm.Machine(
    name="serious_injury", state_attr="status", initial="SUBMITTED",
    transitions=(
        sm.T("SUBMITTED", "accept", "RAF_ACCEPTED", ("MEDICAL_OFFICER",)),
        sm.T("SUBMITTED", "reject", "RAF_REJECTED", ("MEDICAL_OFFICER",)),
        sm.T("RAF_REJECTED", "appeal", "HPCSA_APPEAL", ("LEGAL",)),
        sm.T("HPCSA_APPEAL", "uphold", "UPHELD", ("LEGAL",)),
        sm.T("HPCSA_APPEAL", "dismiss", "DISMISSED", ("LEGAL",)),
    ),
)


def create(db: Session, claim_id: str, list_match: bool = False,
           wpi: Optional[float] = None, narrative: bool = False) -> "models.SeriousInjury":
    si = models.SeriousInjury(claim_id=claim_id, status="SUBMITTED",
                              list_match=list_match, wpi=wpi, narrative=narrative)
    db.add(si)
    db.flush()
    db.commit()
    return si


def transition(db: Session, si_id: int, action: str, user: dict) -> "models.SeriousInjury":
    si = db.get(models.SeriousInjury, si_id)
    if si is None:
        raise sm.IllegalTransition(f"no serious-injury record {si_id}")
    sm.fire(db, SI, si, si_id, action, user)
    db.commit()
    return si


def history(db: Session, si_id: int) -> list:
    return list(db.scalars(
        select(models.TransitionLog)
        .where(models.TransitionLog.entity_type == "serious_injury",
               models.TransitionLog.entity_id == str(si_id))
        .order_by(models.TransitionLog.id)))
