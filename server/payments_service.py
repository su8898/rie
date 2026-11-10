"""Payment batches (domain-logic §8e).

Batch lifecycle OPEN -> APPROVED -> PAID / CANCELLED, enforced by the shared state-machine
primitive. Segregation of duties is three-way: assembler, approver and payer must all differ.
Instructions are gated on eligibility (settled/court-order for those sources; an eligible-to-pay
determination for supplier/undertaking; accepted merits for interim s17(6)) and on payee
verification; the amount is never free-form — it must equal the assembled offer (settlement /
court order) or the determination's net payable (supplier / undertaking), and an interim payment
is capped by it; a claim gets ONE settlement-family and ONE supplier instruction across all
non-cancelled batches (no double payment). Every money event appends to payment_event; paying a
settlement/court-order instruction advances the claim lifecycle to PAID.
"""
from __future__ import annotations

import math
from typing import Optional

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from . import lifecycle_service, models, remittance_service, statemachine as sm

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
_ONE_SHOT_SOURCES = _SETTLEMENT_SOURCES | {"SUPPLIER"}      # paid once per claim, ever
_CENTS = 0.005


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


def _assembled_offer_total(db, claim_id) -> Optional[float]:
    o = db.scalar(select(models.Offer)
                  .where(models.Offer.claim_id == claim_id, models.Offer.status == "ASSEMBLED")
                  .order_by(desc(models.Offer.id)))
    return None if o is None else o.total


def _existing_instruction(db, claim_id: str, sources: set[str]) -> Optional["models.PaymentInstruction"]:
    """An instruction for this claim under any of `sources` in a batch that is not CANCELLED."""
    return db.scalar(
        select(models.PaymentInstruction)
        .join(models.PaymentBatch, models.PaymentBatch.id == models.PaymentInstruction.batch_id)
        .where(models.PaymentInstruction.claim_id == claim_id,
               models.PaymentInstruction.source.in_(sources),
               models.PaymentBatch.status != "CANCELLED")
        .order_by(models.PaymentInstruction.id))


def _resolve_amount(source: str, requested: Optional[float], expected: Optional[float],
                    cap: Optional[float]) -> float:
    """The rand an instruction may carry. `expected` (offer total / net payable) is authoritative
    for every source but INTERIM, which must be explicit and within `cap`. Never negative, never
    zero, never NaN/inf."""
    if requested is not None:
        try:
            amt = float(requested)
        except (TypeError, ValueError):
            raise sm.GateNotMet("amount must be a number")
        if not math.isfinite(amt) or amt <= 0:
            raise sm.GateNotMet("amount must be a positive rand value")
        amt = round(amt, 2)
    else:
        amt = None
    if source == "INTERIM":
        if amt is None:
            raise sm.GateNotMet("an interim (s17(6)) payment requires an explicit amount")
        if cap is None or amt > cap + _CENTS:
            raise sm.GateNotMet(f"interim amount R{amt:,.2f} exceeds the payable R{(cap or 0.0):,.2f}")
        return amt
    if expected is None or expected <= 0:
        raise sm.GateNotMet(f"nothing payable for source {source}")
    expected = round(expected, 2)
    if amt is None:
        return expected
    if abs(amt - expected) > _CENTS:
        raise sm.GateNotMet(
            f"amount R{amt:,.2f} does not match the {source.replace('_', ' ').lower()} amount R{expected:,.2f}")
    return expected


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
    expected: Optional[float] = None
    if source in _SETTLEMENT_SOURCES:
        lc = db.get(models.ClaimLifecycle, claim_id)
        if lc is None or lc.stage not in ("SETTLED", "COURT_ORDER"):
            raise sm.GateNotMet("claim not settled / no court order")
        expected = _assembled_offer_total(db, claim_id)
        if expected is None:
            raise sm.GateNotMet("no assembled offer — the settlement amount comes from the offer")
    elif source == "INTERIM":                                   # s17(6) — merits accepted, quantum open
        m = db.get(models.MeritsDetermination, claim_id)
        if m is None or m.status != "ACCEPTED":
            raise sm.GateNotMet("interim payment requires accepted merits")
    else:                                                       # SUPPLIER / UNDERTAKING_INVOICE
        if det is None or not det.eligible_to_pay:
            raise sm.GateNotMet("claim not eligible to pay")
        expected = det.net_payable

    if source in _ONE_SHOT_SOURCES:                             # pay once — across every live batch
        family = _SETTLEMENT_SOURCES if source in _SETTLEMENT_SOURCES else {source}
        dup = _existing_instruction(db, claim_id, family)
        if dup is not None:
            raise sm.GateNotMet(
                f"claim {claim_id} already has a {dup.source} instruction in batch {dup.batch_id}"
                f"{' (paid)' if dup.paid else ''} — a claim is paid once")

    amt = _resolve_amount(source, amount, expected, det.net_payable if det else None)
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
    if user.get("username") in (b.created_by, b.approved_by):  # three-way segregation of duties
        raise sm.WrongActor("segregation of duties: the payer must differ from the assembler and the approver")
    insts = _instructions(db, batch_id)
    for inst in insts:                                          # every settlement must still be payable
        if inst.source in _SETTLEMENT_SOURCES:
            lc = db.get(models.ClaimLifecycle, inst.claim_id)
            if lc is None or lc.stage not in ("SETTLED", "COURT_ORDER"):
                raise sm.GateNotMet(
                    f"claim {inst.claim_id} is {'missing' if lc is None else lc.stage}, not SETTLED/COURT_ORDER"
                    " — cancel the batch and re-assemble")
    sm.fire(db, BATCH, b, batch_id, "pay", user)               # compare-and-set: a second payer is refused
    b.paid_by = user["username"]
    total = 0.0
    for inst in insts:
        inst.paid = True
        total += inst.amount
        if inst.source in _SETTLEMENT_SOURCES:                  # execute the lifecycle's payment
            lc = db.get(models.ClaimLifecycle, inst.claim_id)
            sm.fire(db, lifecycle_service.LIFECYCLE, lc, inst.claim_id, "pay", user)
    db.add(models.PaymentEvent(batch_id=batch_id, event="PAID", actor=user["username"],
                               role=user["role"], amount=round(total, 2)))
    db.flush()
    remittance_service.issue_for_batch(db, b, user)             # one advice per provider paid
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
        if det.eligible_to_pay and det.net_payable > 0 and det.claim_id not in paid_claims:
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
