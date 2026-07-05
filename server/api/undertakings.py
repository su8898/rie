"""Undertaking router — issue an undertaking, drive its state machine, and manage its invoices.

Paths use literal segments (`/state/`, `/invoices/`) so integer ids never collide with action names:
POST /undertakings                          issue
GET  /undertakings/{u_id}                   read (state + invoices + actions + history)
POST /undertakings/{u_id}/state/{action}    activate|suspend|resume|terminate|lapse
POST /undertakings/{u_id}/invoices          submit an invoice
POST /undertakings/invoices/{inv_id}/adjudicate       adjudicate (set payable)
POST /undertakings/invoices/{inv_id}/state/{action}   approve|reject|pay
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, undertaking_service as svc
from ..db import get_db
from .deps import current_user, require_role

router = APIRouter(prefix="/undertakings")


def _log(x) -> dict:
    return {"from": x.from_state, "to": x.to_state, "action": x.action, "actor": x.actor,
            "role": x.role, "at": x.at.isoformat() if x.at else None, "detail": x.detail}


def _inv_dict(inv) -> dict:
    return {"id": inv.id, "undertaking_id": inv.undertaking_id, "status": inv.status,
            "billed": inv.billed, "payable": inv.payable, "reasons": inv.reasons,
            "actions": svc.INVOICE.actions_from(inv.status)}


def _u_dict(u) -> dict:
    return {"id": u.id, "claim_id": u.claim_id, "origin": u.origin, "status": u.status,
            "scope_dx": u.scope_dx}


@router.post("")
def issue(body: dict = Body(...), db: Session = Depends(get_db),
          user: dict = Depends(require_role("HANDLER", "MEDICAL_OFFICER"))) -> dict:
    u = svc.issue(db, body.get("claim_id"), body.get("origin"), body.get("scope_dx"), user)
    return _u_dict(u)


@router.get("/{u_id}")
def get_undertaking(u_id: int, db: Session = Depends(get_db),
                    user: dict = Depends(current_user)) -> dict:
    u = db.get(models.Undertaking, u_id)
    if u is None:
        raise HTTPException(status_code=404, detail="undertaking not found")
    return {**_u_dict(u),
            "actions": svc.UNDERTAKING.actions_from(u.status),
            "invoices": [_inv_dict(i) for i in svc.invoices_for(db, u_id)],
            "history": [_log(x) for x in svc.history(db, "undertaking", u_id)]}


@router.post("/{u_id}/state/{action}")
def transition(u_id: int, action: str, db: Session = Depends(get_db),
               user: dict = Depends(current_user)) -> dict:
    u = svc.transition(db, u_id, action, user)
    return {**_u_dict(u), "actions": svc.UNDERTAKING.actions_from(u.status)}


@router.post("/{u_id}/invoices")
def submit_invoice(u_id: int, body: dict = Body(default={}), db: Session = Depends(get_db),
                   user: dict = Depends(require_role("MEDICAL_OFFICER"))) -> dict:
    inv = svc.submit_invoice(db, u_id, body.get("billed", 0.0), body.get("dx", ""), user)
    return _inv_dict(inv)


@router.post("/invoices/{inv_id}/adjudicate")
def adjudicate_invoice(inv_id: int, body: dict = Body(default={}), db: Session = Depends(get_db),
                       user: dict = Depends(require_role("MEDICAL_OFFICER"))) -> dict:
    inv = svc.adjudicate_invoice(db, inv_id, body.get("approved", 0.0), user)
    return _inv_dict(inv)


@router.post("/invoices/{inv_id}/state/{action}")
def invoice_transition(inv_id: int, action: str, db: Session = Depends(get_db),
                       user: dict = Depends(current_user)) -> dict:
    inv = svc.invoice_transition(db, inv_id, action, user)
    return _inv_dict(inv)
