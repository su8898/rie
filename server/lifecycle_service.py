"""Claim lifecycle state machine (domain-logic §8a).

LODGED → VALIDATED → MERITS → QUANTUM → OFFER_MADE → SETTLED → PAID → FINALIZED, with
REPUDIATED / LITIGATION / COURT_ORDER branches. 🔒 gates: validate needs s24 (a validated
determination); accept_merits needs an accepted merits determination; make_offer needs an
assembled offer.
"""
from __future__ import annotations

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from . import models, notifications_service, statemachine as sm

LIFECYCLE = sm.Machine(
    name="claim_lifecycle", state_attr="stage", initial="LODGED",
    terminal=frozenset({"REJECTED_COMPLIANCE", "FINALIZED"}),
    transitions=(
        sm.T("LODGED", "validate", "VALIDATED", ("HANDLER",)),
        sm.T("LODGED", "reject_compliance", "REJECTED_COMPLIANCE", ("HANDLER",)),
        sm.T("VALIDATED", "open_merits", "MERITS", ("HANDLER",)),
        sm.T("MERITS", "accept_merits", "QUANTUM", ("HANDLER", "LEGAL")),
        sm.T("MERITS", "repudiate", "REPUDIATED", ("HANDLER", "LEGAL")),
        sm.T("REPUDIATED", "litigate", "LITIGATION", ("LEGAL",)),
        sm.T("QUANTUM", "make_offer", "OFFER_MADE", ("HANDLER",)),
        sm.T("OFFER_MADE", "settle", "SETTLED", ("HANDLER", "LEGAL")),
        sm.T("OFFER_MADE", "litigate", "LITIGATION", ("LEGAL",)),
        sm.T("LITIGATION", "settle", "SETTLED", ("LEGAL",)),
        sm.T("LITIGATION", "court_order", "COURT_ORDER", ("LEGAL",)),
        sm.T("SETTLED", "pay", "PAID", ("ADMIN",)),
        sm.T("COURT_ORDER", "pay", "PAID", ("ADMIN",)),
        sm.T("PAID", "finalize", "FINALIZED", ("HANDLER", "ADMIN")),
    ),
)


def get_or_create(db: Session, claim_id: str) -> "models.ClaimLifecycle":
    lc = db.get(models.ClaimLifecycle, claim_id)
    if lc is None:
        lc = models.ClaimLifecycle(claim_id=claim_id, stage="LODGED")
        db.add(lc)
        db.flush()
    return lc


def _latest_determination(db, claim_id):
    return db.scalar(select(models.Determination)
                     .where(models.Determination.claim_id == claim_id)
                     .order_by(desc(models.Determination.id)))


def _gate_validated(db, claim_id):
    det = _latest_determination(db, claim_id)
    if det is None or not det.validated:
        raise sm.GateNotMet("s24 checklist incomplete — claim not validated")


def _gate_merits_accepted(db, claim_id):
    m = db.get(models.MeritsDetermination, claim_id)
    if m is None or m.status != "ACCEPTED":
        raise sm.GateNotMet("merits not accepted")


def _gate_offer_assembled(db, claim_id):
    o = db.scalar(select(models.Offer)
                  .where(models.Offer.claim_id == claim_id, models.Offer.status == "ASSEMBLED"))
    if o is None:
        raise sm.GateNotMet("no assembled offer — build the offer first")


_GATES = {"validate": _gate_validated, "accept_merits": _gate_merits_accepted,
          "make_offer": _gate_offer_assembled}


def transition(db: Session, claim_id: str, action: str, user: dict) -> "models.ClaimLifecycle":
    lc = db.get(models.ClaimLifecycle, claim_id)
    if lc is None:
        raise sm.IllegalTransition(f"no lifecycle for claim {claim_id}")
    g = _GATES.get(action)
    gate = (lambda: g(db, claim_id)) if g else None
    sm.fire(db, LIFECYCLE, lc, claim_id, action, user, gate=gate)
    notifications_service.emit(db, lc.stage, claim_id)   # §12.8 — POPIA-minimal claimant notice
    db.commit()
    return lc


def history(db: Session, claim_id: str) -> list:
    return list(db.scalars(
        select(models.TransitionLog)
        .where(models.TransitionLog.entity_type == "claim_lifecycle",
               models.TransitionLog.entity_id == str(claim_id))
        .order_by(models.TransitionLog.id)))
