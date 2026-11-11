"""Notifications (domain-logic §12.8) — the POPIA-minimal outbox + opt-in channel preferences.

Static /prefs routes are declared before /{notif_id} so they are not shadowed.
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import notifications_service as svc, work_query
from ..db import get_db
from .deps import current_user

router = APIRouter(prefix="/notifications")


@router.get("")
def outbox(status: str | None = None, claim_id: str | None = None,
           limit: int = Query(200, ge=1, le=1000), db: Session = Depends(get_db),
           user: dict = Depends(current_user)) -> list[dict]:
    return svc.outbox(db, status=status, claim_id=claim_id, limit=limit)


@router.get("/search")
def search(q: str = Query("", max_length=100), status: str = "", channel: str = "", event: str = "",
           claim_id: str = Query("", max_length=64), limit: int = Query(25, ge=1, le=200),
           offset: int = Query(0, ge=0), db: Session = Depends(get_db),
           user: dict = Depends(current_user)) -> dict:
    """The notification outbox as a worklist: `{rows, total, counts, events}`."""
    return work_query.search_notifications(db, q=q, status=status, channel=channel, event=event,
                                           claim_id=claim_id, limit=limit, offset=offset)


@router.get("/prefs/{party_token}")
def get_pref(party_token: str, db: Session = Depends(get_db),
             user: dict = Depends(current_user)) -> dict:
    return svc.get_pref(db, party_token) or {"party_token": party_token, "channel": "NONE",
                                             "opted_in": False}


@router.post("/prefs/{party_token}")
def set_pref(party_token: str, body: dict = Body(...), db: Session = Depends(get_db),
             user: dict = Depends(current_user)) -> dict:
    try:
        return svc.set_pref(db, party_token, body.get("channel", "NONE"),
                            bool(body.get("opted_in", False)))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{notif_id}/sent")
def mark_sent(notif_id: int, db: Session = Depends(get_db),
              user: dict = Depends(current_user)) -> dict:
    try:
        return svc.mark_sent(db, notif_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{notif_id}/failed")
def mark_failed(notif_id: int, db: Session = Depends(get_db),
                user: dict = Depends(current_user)) -> dict:
    try:
        return svc.mark_failed(db, notif_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
