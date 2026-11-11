"""Undertaking + invoice state machines (domain-logic §8c).

An undertaking (settlement or emergency) is ISSUED, then ACTIVE, and may be SUSPENDED / resumed,
TERMINATED, or LAPSED. While ACTIVE it accepts invoices: each invoice is RECEIVED → ADJUDICATED →
PAYABLE → PAID (or ADJUDICATED → REJECTED). 🔒 gate: an invoice may only be submitted against an
ACTIVE undertaking; a diagnosis outside the undertaking's scope flags UNDERTAKING_SCOPE.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models, statemachine as sm

UNDERTAKING = sm.Machine(
    name="undertaking", state_attr="status", initial="ISSUED",
    terminal=frozenset({"TERMINATED", "LAPSED"}),
    transitions=(
        sm.T("ISSUED", "activate", "ACTIVE", ("HANDLER", "MEDICAL_OFFICER")),
        sm.T("ACTIVE", "suspend", "SUSPENDED", ("INVESTIGATOR", "MEDICAL_OFFICER")),
        sm.T("SUSPENDED", "resume", "ACTIVE", ("INVESTIGATOR", "MEDICAL_OFFICER")),
        sm.T("ACTIVE", "terminate", "TERMINATED", ("ADMIN", "MEDICAL_OFFICER")),
        sm.T("ACTIVE", "lapse", "LAPSED", ("ADMIN",)),
    ),
)

INVOICE = sm.Machine(
    name="undertaking_invoice", state_attr="status", initial="RECEIVED",
    terminal=frozenset({"REJECTED", "PAID"}),
    transitions=(
        sm.T("RECEIVED", "adjudicate", "ADJUDICATED", ("MEDICAL_OFFICER",)),
        sm.T("ADJUDICATED", "approve", "PAYABLE", ("MEDICAL_OFFICER",)),
        sm.T("ADJUDICATED", "reject", "REJECTED", ("MEDICAL_OFFICER",)),
        sm.T("PAYABLE", "pay", "PAID", ("ADMIN",)),
    ),
)


def issue(db: Session, claim_id: str, origin: str, scope_dx, user: dict) -> "models.Undertaking":
    if origin not in ("SETTLEMENT", "EMERGENCY"):
        raise sm.IllegalTransition(f"undertaking origin must be SETTLEMENT or EMERGENCY, not {origin!r}")
    u = models.Undertaking(claim_id=claim_id, origin=origin, status="ISSUED", scope_dx=scope_dx or [])
    db.add(u)
    db.commit()
    return u


def transition(db: Session, u_id: int, action: str, user: dict) -> "models.Undertaking":
    u = db.get(models.Undertaking, u_id)
    if u is None:
        raise sm.IllegalTransition(f"no undertaking {u_id}")
    sm.fire(db, UNDERTAKING, u, u_id, action, user)
    db.commit()
    return u


def submit_invoice(db: Session, u_id: int, billed: float, dx: str,
                   user: dict) -> "models.UndertakingInvoice":
    u = db.get(models.Undertaking, u_id)
    if u is None:
        raise sm.IllegalTransition(f"no undertaking {u_id}")
    if u.status != "ACTIVE":
        raise sm.GateNotMet("undertaking not active")
    reasons: list = []
    if (dx or "")[:3] not in {(d or "")[:3] for d in u.scope_dx}:
        reasons = ["UNDERTAKING_SCOPE"]
    inv = models.UndertakingInvoice(undertaking_id=u_id, status="RECEIVED",
                                    billed=billed, payable=0.0, reasons=reasons)
    db.add(inv)
    db.commit()
    return inv


def adjudicate_invoice(db: Session, inv_id: int, approved: float,
                       user: dict) -> "models.UndertakingInvoice":
    inv = db.get(models.UndertakingInvoice, inv_id)
    if inv is None:
        raise sm.IllegalTransition(f"no invoice {inv_id}")
    try:
        amount = round(float(approved), 2)
    except (TypeError, ValueError):
        raise sm.GateNotMet("the approved amount must be a number") from None
    if not 0 <= amount <= round(float(inv.billed or 0.0), 2):      # never more than was billed
        raise sm.GateNotMet("the approved amount must be between zero and the amount billed")
    sm.fire(db, INVOICE, inv, inv_id, "adjudicate", user, detail={"approved": amount})
    inv.payable = amount
    db.commit()
    return inv


def invoice_transition(db: Session, inv_id: int, action: str,
                       user: dict) -> "models.UndertakingInvoice":
    inv = db.get(models.UndertakingInvoice, inv_id)
    if inv is None:
        raise sm.IllegalTransition(f"no invoice {inv_id}")
    sm.fire(db, INVOICE, inv, inv_id, action, user)
    db.commit()
    return inv


def invoices_for(db: Session, u_id: int) -> list:
    return list(db.scalars(
        select(models.UndertakingInvoice)
        .where(models.UndertakingInvoice.undertaking_id == u_id)
        .order_by(models.UndertakingInvoice.id)))


def history(db: Session, entity_type: str, entity_id) -> list:
    return list(db.scalars(
        select(models.TransitionLog)
        .where(models.TransitionLog.entity_type == entity_type,
               models.TransitionLog.entity_id == str(entity_id))
        .order_by(models.TransitionLog.id)))
