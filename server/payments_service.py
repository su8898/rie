"""Payment batches (domain-logic §8e).

Batch lifecycle OPEN -> APPROVED -> PAID / CANCELLED, enforced by the shared state-machine
primitive. Segregation of duties: the approver must differ from the assembler. Instructions are
gated on eligibility (settled/court-order for those sources; an eligible-to-pay determination
for supplier/undertaking; accepted merits for interim s17(6)) and on payee verification. Every
money event appends to payment_event; paying a settlement/court-order instruction advances the
claim lifecycle to PAID.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from . import lifecycle_service, models, statemachine as sm

BATCH = sm.Machine(
    name="payment_batch", state_attr="status", initial="OPEN",
    terminal=frozenset({"PAID", "CANCELLED"}),
    transitions=(
        sm.T("OPEN", "approve", "APPROVED", ("ADMIN",)),
        sm.T("OPEN", "cancel", "CANCELLED", ("ADMIN", "HANDLER")),
        sm.T("APPROVED", "pay", "PAID", ("ADMIN",)),
        sm.T("APPROVED", "cancel", "CANCELLED", ("ADMIN",)),
    ),
)

VALID_SOURCES = {"SETTLEMENT", "COURT_ORDER", "UNDERTAKING_INVOICE", "SUPPLIER", "INTERIM"}
_SETTLEMENT_SOURCES = {"SETTLEMENT", "COURT_ORDER"}


def _instructions(db, batch_id):
    return list(db.scalars(select(models.PaymentInstruction)
                           .where(models.PaymentInstruction.batch_id == batch_id)
                           .order_by(models.PaymentInstruction.id)))


def _total(db, batch_id) -> float:
    return round(sum(i.amount for i in _instructions(db, batch_id)), 2)


def _latest_det(db, claim_id):
    return db.scalar(select(models.Determination)
                     .where(models.Determination.claim_id == claim_id)
                     .order_by(desc(models.Determination.id)))


def create_batch(db: Session, user: dict, note: Optional[str] = None) -> "models.PaymentBatch":
    b = models.PaymentBatch(status="OPEN", created_by=user["username"], note=note)
    db.add(b)
    db.flush()
    db.add(models.PaymentEvent(batch_id=b.id, event="CREATED", actor=user["username"],
                               role=user["role"], amount=None))
    db.commit()
    return b


def add_instruction(db: Session, batch_id: int, claim_id: str, source: str,
                    amount: Optional[float], user: dict) -> "models.PaymentInstruction":
    b = db.get(models.PaymentBatch, batch_id)
    if b is None:
        raise sm.IllegalTransition("no such payment batch")
    if b.status != "OPEN":
        raise sm.GateNotMet("batch is not OPEN")
    if source not in VALID_SOURCES:
        raise sm.GateNotMet(f"invalid instruction source: {source}")

    claim = db.get(models.ClaimRecord, claim_id)
    if claim is None:
        raise sm.GateNotMet(f"claim {claim_id} not found")
    if not (claim.raw or {}).get("payee_verified"):
        raise sm.GateNotMet("PAYEE_UNVERIFIED — payee not verified")

    det = _latest_det(db, claim_id)
    if source in _SETTLEMENT_SOURCES:
        lc = db.get(models.ClaimLifecycle, claim_id)
        if lc is None or lc.stage not in ("SETTLED", "COURT_ORDER"):
            raise sm.GateNotMet("claim not settled / no court order")
    elif source == "INTERIM":                                   # s17(6) — merits accepted, quantum open
        m = db.get(models.MeritsDetermination, claim_id)
        if m is None or m.status != "ACCEPTED":
            raise sm.GateNotMet("interim payment requires accepted merits")
    else:                                                       # SUPPLIER / UNDERTAKING_INVOICE
        if det is None or not det.eligible_to_pay:
            raise sm.GateNotMet("claim not eligible to pay")

    amt = float(amount) if amount is not None else (det.net_payable if det else 0.0)
    inst = models.PaymentInstruction(batch_id=batch_id, claim_id=claim_id, source=source,
                                     amount=amt, paid=False)
    db.add(inst)
    db.flush()
    db.add(models.PaymentEvent(batch_id=batch_id, event="INSTRUCTION_ADDED", actor=user["username"],
                               role=user["role"], amount=amt,
                               detail={"claim_id": claim_id, "source": source}))
    db.commit()
    return inst


def approve(db: Session, batch_id: int, user: dict) -> "models.PaymentBatch":
    b = db.get(models.PaymentBatch, batch_id)
    if b is None:
        raise sm.IllegalTransition("no such payment batch")
    if user.get("username") == b.created_by:                    # segregation of duties
        raise sm.WrongActor("segregation of duties: the approver must differ from the assembler")
    if not _instructions(db, batch_id):
        raise sm.GateNotMet("cannot approve an empty batch")
    sm.fire(db, BATCH, b, batch_id, "approve", user)
    b.approved_by = user["username"]
    db.add(models.PaymentEvent(batch_id=batch_id, event="APPROVED", actor=user["username"],
                               role=user["role"], amount=_total(db, batch_id)))
    db.commit()
    return b


def pay(db: Session, batch_id: int, user: dict) -> "models.PaymentBatch":
    b = db.get(models.PaymentBatch, batch_id)
    if b is None:
        raise sm.IllegalTransition("no such payment batch")
    sm.fire(db, BATCH, b, batch_id, "pay", user)
    b.paid_by = user["username"]
    total = 0.0
    for inst in _instructions(db, batch_id):
        inst.paid = True
        total += inst.amount
        if inst.source in _SETTLEMENT_SOURCES:                  # execute the lifecycle's payment
            lc = db.get(models.ClaimLifecycle, inst.claim_id)
            if lc is not None and lc.stage in ("SETTLED", "COURT_ORDER"):
                sm.fire(db, lifecycle_service.LIFECYCLE, lc, inst.claim_id, "pay", user)
    db.add(models.PaymentEvent(batch_id=batch_id, event="PAID", actor=user["username"],
                               role=user["role"], amount=round(total, 2)))
    db.commit()
    return b


def cancel(db: Session, batch_id: int, user: dict) -> "models.PaymentBatch":
    b = db.get(models.PaymentBatch, batch_id)
    if b is None:
        raise sm.IllegalTransition("no such payment batch")
    sm.fire(db, BATCH, b, batch_id, "cancel", user)
    db.add(models.PaymentEvent(batch_id=batch_id, event="CANCELLED", actor=user["username"],
                               role=user["role"], amount=None))
    db.commit()
    return b


def queue(db: Session) -> list[dict]:
    """Claims whose latest determination is eligible to pay and not yet in a paid instruction."""
    paid_claims = set(db.scalars(select(models.PaymentInstruction.claim_id)
                                 .where(models.PaymentInstruction.paid.is_(True))))
    out = []
    seen = set()
    for det in db.scalars(select(models.Determination).order_by(desc(models.Determination.id))):
        if det.claim_id in seen:
            continue
        seen.add(det.claim_id)
        if det.eligible_to_pay and det.claim_id not in paid_claims:
            out.append({"claim_id": det.claim_id, "net_payable": det.net_payable,
                        "disposition": det.disposition, "band": det.band})
    return out


def batch_dict(db: Session, b: "models.PaymentBatch") -> dict:
    return {
        "id": b.id, "status": b.status, "created_by": b.created_by,
        "approved_by": b.approved_by, "paid_by": b.paid_by, "note": b.note,
        "total": _total(db, b.id), "actions": BATCH.actions_from(b.status),
        "instructions": [{"id": i.id, "claim_id": i.claim_id, "source": i.source,
                          "amount": i.amount, "paid": i.paid} for i in _instructions(db, b.id)],
        "events": [{"event": e.event, "actor": e.actor, "role": e.role, "amount": e.amount,
                    "at": e.at.isoformat() if e.at else None, "detail": e.detail}
                   for e in db.scalars(select(models.PaymentEvent)
                                       .where(models.PaymentEvent.batch_id == b.id)
                                       .order_by(models.PaymentEvent.id))],
    }
