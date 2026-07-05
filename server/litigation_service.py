"""Litigation state machine (domain-logic §8d).

SUMMONS_SERVED → PLEADINGS → TRIAL_SET → SETTLED / JUDGMENT → ORDER_PAID → CLOSED. From
PLEADINGS a missed-pleadings default_judgment jumps straight to JUDGMENT (and stamps the record's
default_judgment flag). Settlement and judgment both converge on ORDER_PAID, which admin then
closes. Role enforcement on transitions happens inside sm.fire.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models, statemachine as sm

LITIGATION = sm.Machine(
    name="litigation", state_attr="status", initial="SUMMONS_SERVED",
    terminal=frozenset({"CLOSED"}),
    transitions=(
        sm.T("SUMMONS_SERVED", "plead", "PLEADINGS", ("LEGAL",)),
        sm.T("PLEADINGS", "set_trial", "TRIAL_SET", ("LEGAL",)),
        sm.T("PLEADINGS", "default_judgment", "JUDGMENT", ("LEGAL", "ADMIN")),
        sm.T("TRIAL_SET", "settle", "SETTLED", ("LEGAL",)),
        sm.T("TRIAL_SET", "judgment", "JUDGMENT", ("LEGAL",)),
        sm.T("SETTLED", "order_paid", "ORDER_PAID", ("ADMIN",)),
        sm.T("JUDGMENT", "order_paid", "ORDER_PAID", ("ADMIN",)),
        sm.T("ORDER_PAID", "close", "CLOSED", ("LEGAL", "ADMIN")),
    ),
)


def create(db: Session, claim_id: str, user: dict) -> "models.Litigation":
    lit = models.Litigation(claim_id=claim_id, status="SUMMONS_SERVED", default_judgment=False)
    db.add(lit)
    db.flush()
    db.commit()
    return lit


def transition(db: Session, lit_id: int, action: str, user: dict) -> "models.Litigation":
    lit = db.get(models.Litigation, lit_id)
    if lit is None:
        raise sm.IllegalTransition(f"no litigation record {lit_id}")
    sm.fire(db, LITIGATION, lit, lit_id, action, user)
    if action == "default_judgment":
        lit.default_judgment = True
    db.commit()
    return lit


def history(db: Session, lit_id: int) -> list:
    return list(db.scalars(
        select(models.TransitionLog)
        .where(models.TransitionLog.entity_type == "litigation",
               models.TransitionLog.entity_id == str(lit_id))
        .order_by(models.TransitionLog.id)))
