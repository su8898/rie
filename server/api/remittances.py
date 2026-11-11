"""Remittance advice for the Fund's operators — list, read, print, and issue for a paid batch.

The provider's own access is over the rails channel (/rails/v1/remittances)."""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from .. import remittance_service as svc
from ..db import get_db
from .deps import current_user, require_role

router = APIRouter(prefix="/remittances")

# The print page is static markup: no script, no outside resource, nothing framed.
_PRINT_CSP = "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'"


def _call(fn, *args):
    try:
        return fn(*args)
    except svc.RemittanceError as e:
        raise HTTPException(status_code=e.status, detail=e.detail) from None


@router.get("")
def list_remittances(provider_id: Optional[str] = None, date_from: Optional[date] = None,
                     date_to: Optional[date] = None, limit: int = Query(200, ge=1, le=1000),
                     db: Session = Depends(get_db), user: dict = Depends(current_user)) -> list[dict]:
    return svc.list_remittances(db, provider_id, date_from, date_to, limit)


@router.get("/search")
def search_remittances(provider_id: Optional[str] = None,
                       status: Optional[str] = Query(None, pattern="^(REMITTED|ACKNOWLEDGED)$"),
                       batch_id: Optional[int] = None, q: Optional[str] = Query(None, max_length=100),
                       date_from: Optional[date] = None, date_to: Optional[date] = None,
                       limit: int = Query(25, ge=1, le=200), offset: int = Query(0, ge=0),
                       db: Session = Depends(get_db), user: dict = Depends(current_user)) -> dict:
    """The remittance worklist for the operator screens: `{rows, total}`."""
    rows, total = svc.search(db, provider_id=provider_id, status=status, batch_id=batch_id, q=q,
                             date_from=date_from, date_to=date_to, limit=limit, offset=offset)
    return {"rows": rows, "total": total}


@router.post("/issue/{batch_id}")
def issue(batch_id: int, db: Session = Depends(get_db),
          user: dict = Depends(require_role("ADMIN"))) -> list[dict]:
    return _call(svc.issue, db, batch_id, user)


@router.get("/{ref}")
def get_remittance(ref: str, db: Session = Depends(get_db),
                   user: dict = Depends(current_user)) -> dict:
    return _call(svc.detail, db, ref)


@router.get("/{ref}/xml")
def remittance_xml(ref: str, db: Session = Depends(get_db),
                   user: dict = Depends(current_user)) -> Response:
    return Response(content=svc.to_xml(_call(svc.detail, db, ref)), media_type="application/xml")


@router.get("/{ref}/print", response_class=HTMLResponse)
def remittance_print(ref: str, db: Session = Depends(get_db),
                     user: dict = Depends(current_user)) -> HTMLResponse:
    return HTMLResponse(svc.print_html(_call(svc.detail, db, ref)),
                        headers={"Content-Security-Policy": _PRINT_CSP})
