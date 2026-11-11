"""Payment batches (domain-logic §8e).

Batch lifecycle OPEN -> APPROVED -> PAID / CANCELLED, enforced by the shared state-machine
primitive. Segregation of duties is three-way: assembler, approver and payer must all differ.
Instructions are gated on eligibility (settled/court-order for those sources; an eligible-to-pay
determination for supplier/undertaking; accepted merits for interim s17(6)) and on payee
verification; the amount is never free-form — it must equal the assembled offer (settlement /
court order) or the determination's net payable (supplier / undertaking), and an interim payment
is capped by it; a claim gets ONE settlement-family and ONE supplier instruction across all
non-cancelled batches (no double payment). Every money event appends to payment_event; paying a
settlement/court-order instruction advances the claim lifecycle to PAID. While a batch is OPEN its
assembler side may still correct it: remove an instruction or change the note (both logged).
"""
from __future__ import annotations

import math
from typing import Optional

from sqlalchemy import desc, func, or_, select
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


def remove_instruction(db: Session, batch_id: int, instruction_id: int, user: dict) -> "models.PaymentBatch":
    """Take a claim out of a batch that is still OPEN. The removal is logged; the claim returns to
    the queue and may be instructed again."""
    b = db.get(models.PaymentBatch, batch_id)
    if b is None:
        raise sm.IllegalTransition("no such payment batch")
    if b.status != "OPEN":
        raise sm.GateNotMet("batch is not OPEN")
    inst = db.get(models.PaymentInstruction, instruction_id)
    if inst is None or inst.batch_id != batch_id:
        raise sm.IllegalTransition("no such instruction in this batch")
    db.add(models.PaymentEvent(batch_id=batch_id, event="INSTRUCTION_REMOVED", actor=user["username"],
                               role=user["role"], amount=inst.amount,
                               detail={"claim_id": inst.claim_id, "source": inst.source}))
    db.delete(inst)
    db.commit()
    return b


def set_note(db: Session, batch_id: int, note: Optional[str], user: dict) -> "models.PaymentBatch":
    """Change the note on a batch that is still OPEN (logged)."""
    b = db.get(models.PaymentBatch, batch_id)
    if b is None:
        raise sm.IllegalTransition("no such payment batch")
    if b.status != "OPEN":
        raise sm.GateNotMet("batch is not OPEN")
    note = (note or "").strip() or None
    if note != b.note:
        b.note = note
        db.add(models.PaymentEvent(batch_id=batch_id, event="NOTE_CHANGED", actor=user["username"],
                                   role=user["role"], amount=None, detail={"note": note}))
        db.commit()
    return b


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


def _live_instructions(db, claim_ids) -> dict[str, tuple[int, str]]:
    """claim -> (batch id, batch status) for every claim held by a batch that is not CANCELLED."""
    if not claim_ids:
        return {}
    return {cid: (bid, status) for cid, bid, status in db.execute(
        select(models.PaymentInstruction.claim_id, models.PaymentBatch.id, models.PaymentBatch.status)
        .join(models.PaymentBatch, models.PaymentBatch.id == models.PaymentInstruction.batch_id)
        .where(models.PaymentInstruction.claim_id.in_(claim_ids),
               models.PaymentBatch.status != "CANCELLED")
        .order_by(models.PaymentInstruction.id))}


def _providers(db, claim_ids) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {c: [] for c in claim_ids}
    if claim_ids:
        for cid, provider in db.execute(
                select(models.BillingLineRecord.claim_id, models.BillingLineRecord.provider_id)
                .where(models.BillingLineRecord.claim_id.in_(claim_ids)).distinct()):
            if provider and provider not in out[cid]:
                out[cid].append(provider)
    return out


def queue(db: Session) -> list[dict]:
    """Claims whose latest determination is eligible to pay and not yet in a paid instruction.

    Each row says how the claim would be paid (`source`, `amount`) and, when it cannot be added to
    a batch right now, why (`blocked`) — the same gates add_instruction enforces."""
    paid_claims = set(db.scalars(select(models.PaymentInstruction.claim_id)
                                 .where(models.PaymentInstruction.paid.is_(True))))
    dets = []
    seen = set()
    for det in db.scalars(select(models.Determination).order_by(desc(models.Determination.id))):
        if det.claim_id in seen:
            continue
        seen.add(det.claim_id)
        if det.eligible_to_pay and det.net_payable > 0 and det.claim_id not in paid_claims:
            dets.append(det)
    ids = [d.claim_id for d in dets]
    live, providers = _live_instructions(db, ids), _providers(db, ids)
    out = []
    for det in dets:
        claim = db.get(models.ClaimRecord, det.claim_id)
        row = {"claim_id": det.claim_id, "net_payable": det.net_payable,
               "disposition": det.disposition, "band": det.band,
               "claim_type": claim.claim_type if claim else None,
               "lodged_on": claim.lodged_on.isoformat() if claim and claim.lodged_on else None,
               "providers": providers.get(det.claim_id, []),
               "source": None, "amount": det.net_payable, "blocked": None, "in_batch": None}
        if det.claim_id in live:
            bid, status = live[det.claim_id]
            row["in_batch"] = {"id": bid, "status": status}
            row["blocked"] = "IN_BATCH"
        if claim is None:
            row["blocked"] = row["blocked"] or "NO_CLAIM_RECORD"
        else:
            if claim.claim_type == "PERSONAL":
                lc = db.get(models.ClaimLifecycle, det.claim_id)
                stage = lc.stage if lc else None
                row["source"] = "COURT_ORDER" if stage == "COURT_ORDER" else "SETTLEMENT"
                offer = _assembled_offer_total(db, det.claim_id)
                row["amount"] = offer
                if stage not in ("SETTLED", "COURT_ORDER") or offer is None:
                    row["blocked"] = row["blocked"] or "NOT_SETTLED"
            else:
                row["source"] = claim.claim_type if claim.claim_type in VALID_SOURCES else "SUPPLIER"
            if not (claim.raw or {}).get("payee_verified"):
                row["blocked"] = row["blocked"] or "PAYEE_UNVERIFIED"
        out.append(row)
    return out


def _stamp(dt) -> Optional[str]:
    return dt.isoformat() if dt else None


def batch_summary(db: Session, b: "models.PaymentBatch", n_claims: int, total: float,
                  paid_at=None) -> dict:
    return {"id": b.id, "status": b.status, "created_by": b.created_by,
            "approved_by": b.approved_by, "paid_by": b.paid_by, "note": b.note,
            "created_at": _stamp(b.created_at), "paid_at": _stamp(paid_at),
            "n_claims": n_claims, "total": round(total or 0.0, 2)}


def list_batches(db: Session, *, status: Optional[str] = None, q: Optional[str] = None,
                 direction: str = "desc", limit: int = 25, offset: int = 0) -> tuple[list[dict], int, dict]:
    """The payment-run worklist: one summary row per batch, newest first, with a count per status
    (the counts ignore the status filter, so the saved views can show them)."""
    base = select(models.PaymentBatch)
    if q and (q := q.strip()):
        like = f"%{q}%"
        held = select(models.PaymentInstruction.batch_id).where(models.PaymentInstruction.claim_id.ilike(like))
        conds = [models.PaymentBatch.note.ilike(like), models.PaymentBatch.created_by.ilike(like),
                 models.PaymentBatch.id.in_(held)]
        digits = q.lstrip("#")
        if digits.isdigit():
            conds.append(models.PaymentBatch.id == int(digits))
        base = base.where(or_(*conds))
    counts = dict(db.execute(select(models.PaymentBatch.status, func.count())
                             .where(models.PaymentBatch.id.in_(select(base.subquery().c.id)))
                             .group_by(models.PaymentBatch.status)).all())
    if status:
        base = base.where(models.PaymentBatch.status == status)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    order = models.PaymentBatch.id.asc() if direction == "asc" else models.PaymentBatch.id.desc()
    batches = list(db.scalars(base.order_by(order).limit(limit).offset(offset)))
    ids = [b.id for b in batches]
    agg = {bid: (n, t) for bid, n, t in db.execute(
        select(models.PaymentInstruction.batch_id, func.count(), func.sum(models.PaymentInstruction.amount))
        .where(models.PaymentInstruction.batch_id.in_(ids))
        .group_by(models.PaymentInstruction.batch_id))} if ids else {}
    paid_at = dict(db.execute(select(models.PaymentEvent.batch_id, func.max(models.PaymentEvent.at))
                              .where(models.PaymentEvent.batch_id.in_(ids), models.PaymentEvent.event == "PAID")
                              .group_by(models.PaymentEvent.batch_id)).all()) if ids else {}
    rows = [batch_summary(db, b, *agg.get(b.id, (0, 0.0)), paid_at.get(b.id)) for b in batches]
    return rows, total, {k: counts.get(k, 0) for k in ("OPEN", "APPROVED", "PAID", "CANCELLED")}


def batch_dict(db: Session, b: "models.PaymentBatch") -> dict:
    insts = _instructions(db, b.id)
    ids = [i.claim_id for i in insts]
    providers = _providers(db, ids)
    types = dict(db.execute(select(models.ClaimRecord.claim_id, models.ClaimRecord.claim_type)
                            .where(models.ClaimRecord.claim_id.in_(ids))).all()) if ids else {}
    events = list(db.scalars(select(models.PaymentEvent).where(models.PaymentEvent.batch_id == b.id)
                             .order_by(models.PaymentEvent.id)))
    paid_at = next((e.at for e in reversed(events) if e.event == "PAID"), None)
    return {
        **batch_summary(db, b, len(insts), sum(i.amount for i in insts), paid_at),
        "actions": BATCH.actions_from(b.status),
        "instructions": [{"id": i.id, "claim_id": i.claim_id, "source": i.source,
                          "amount": i.amount, "paid": i.paid, "claim_type": types.get(i.claim_id),
                          "providers": providers.get(i.claim_id, [])} for i in insts],
        "events": [{"event": e.event, "actor": e.actor, "role": e.role, "amount": e.amount,
                    "at": e.at.isoformat() if e.at else None, "detail": e.detail} for e in events],
        "remittances": [remittance_service.summary(r) for r in db.scalars(
            select(models.Remittance).where(models.Remittance.batch_id == b.id)
            .order_by(models.Remittance.id))],
    }
