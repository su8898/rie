"""Payments — the eligible-claim queue and payment batches with segregation of duties.

HANDLER assembles a batch and adds instructions; a *different* ADMIN approves and pays. Every
money event is logged; paying a settlement instruction advances that claim's lifecycle to PAID.
"""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from .. import models, payments_service as svc
from ..db import get_db
from .deps import current_user, require_role

router = APIRouter(prefix="/payments")


class BatchIn(BaseModel):
    note: Optional[str] = Field(default=None, max_length=500)


class InstructionIn(BaseModel):
    claim_id: str = Field(min_length=1, max_length=64)
    source: Literal["SETTLEMENT", "COURT_ORDER", "UNDERTAKING_INVOICE", "SUPPLIER", "INTERIM"]
    amount: Optional[float] = Field(default=None, gt=0, le=1_000_000_000)


@router.get("/queue")
def queue(db: Session = Depends(get_db), user: dict = Depends(current_user)) -> list[dict]:
    return svc.queue(db)


@router.get("/batches")
def list_batches(db: Session = Depends(get_db), user: dict = Depends(current_user)) -> list[dict]:
    return [svc.batch_dict(db, b) for b in
            db.scalars(select(models.PaymentBatch).order_by(desc(models.PaymentBatch.id)))]


@router.get("/runs")
def list_runs(status: Optional[Literal["OPEN", "APPROVED", "PAID", "CANCELLED"]] = None,
              q: Optional[str] = Query(None, max_length=100),
              direction: Literal["asc", "desc"] = "desc",
              limit: int = Query(25, ge=1, le=200), offset: int = Query(0, ge=0),
              db: Session = Depends(get_db), user: dict = Depends(current_user)) -> dict:
    """The payment-run worklist: summary rows, a total for paging and a count per status."""
    rows, total, counts = svc.list_batches(db, status=status, q=q, direction=direction,
                                           limit=limit, offset=offset)
    return {"rows": rows, "total": total, "counts": counts}


@router.post("/batches")
def create_batch(body: BatchIn = BatchIn(), db: Session = Depends(get_db),
                 user: dict = Depends(require_role("HANDLER", "ADMIN"))) -> dict:
    return svc.batch_dict(db, svc.create_batch(db, user, note=body.note))


@router.get("/batches/{batch_id}")
def get_batch(batch_id: int, db: Session = Depends(get_db),
              user: dict = Depends(current_user)) -> dict:
    b = db.get(models.PaymentBatch, batch_id)
    if b is None:
        raise HTTPException(status_code=404, detail="batch not found")
    return svc.batch_dict(db, b)


@router.post("/batches/{batch_id}/instructions")
def add_instruction(batch_id: int, body: InstructionIn, db: Session = Depends(get_db),
                    user: dict = Depends(require_role("HANDLER", "ADMIN"))) -> dict:
    svc.add_instruction(db, batch_id, body.claim_id, body.source, body.amount, user)
    return svc.batch_dict(db, db.get(models.PaymentBatch, batch_id))


@router.delete("/batches/{batch_id}/instructions/{instruction_id}")
def remove_instruction(batch_id: int, instruction_id: int, db: Session = Depends(get_db),
                       user: dict = Depends(require_role("HANDLER", "ADMIN"))) -> dict:
    return svc.batch_dict(db, svc.remove_instruction(db, batch_id, instruction_id, user))


@router.patch("/batches/{batch_id}")
def update_batch(batch_id: int, body: BatchIn, db: Session = Depends(get_db),
                 user: dict = Depends(require_role("HANDLER", "ADMIN"))) -> dict:
    return svc.batch_dict(db, svc.set_note(db, batch_id, body.note, user))


@router.post("/batches/{batch_id}/approve")
def approve(batch_id: int, db: Session = Depends(get_db),
            user: dict = Depends(require_role("ADMIN"))) -> dict:
    return svc.batch_dict(db, svc.approve(db, batch_id, user))


@router.post("/batches/{batch_id}/pay")
def pay(batch_id: int, db: Session = Depends(get_db),
        user: dict = Depends(require_role("ADMIN"))) -> dict:
    return svc.batch_dict(db, svc.pay(db, batch_id, user))


@router.post("/batches/{batch_id}/cancel")
def cancel(batch_id: int, db: Session = Depends(get_db),
           user: dict = Depends(require_role("HANDLER", "ADMIN"))) -> dict:
    return svc.batch_dict(db, svc.cancel(db, batch_id, user))
