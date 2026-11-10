"""Medical reports for the Fund's operators — the forms on file for a claim, to read and print.

Providers file and read their own over the rails channel (/rails/v1/medical-reports)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from .. import medical_report_service as svc
from ..db import get_db
from .deps import current_user

router = APIRouter(prefix="/medical-reports")

# The print page is static markup: no script, no outside resource, nothing framed.
_PRINT_CSP = "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'"


def _call(fn, *args):
    try:
        return fn(*args)
    except svc.ReportError as e:
        raise HTTPException(status_code=e.status, detail=e.detail) from None


@router.get("")
def list_reports(claim_id: Optional[str] = None, provider_id: Optional[str] = None,
                 limit: int = Query(200, ge=1, le=1000), db: Session = Depends(get_db),
                 user: dict = Depends(current_user)) -> list[dict]:
    return svc.list_reports(db, provider_id=provider_id, claim_id=claim_id, limit=limit)


@router.get("/forms")
def forms(user: dict = Depends(current_user)) -> list[dict]:
    return svc.catalogue()


@router.get("/documentation/{claim_id}")
def documentation(claim_id: str, db: Session = Depends(get_db),
                  user: dict = Depends(current_user)) -> dict:
    return _call(svc.documentation, db, claim_id)


@router.get("/{ref}")
def get_report(ref: str, db: Session = Depends(get_db), user: dict = Depends(current_user)) -> dict:
    return _call(svc.get, db, ref)


@router.get("/{ref}/xml")
def report_xml(ref: str, db: Session = Depends(get_db), user: dict = Depends(current_user)) -> Response:
    return Response(content=svc.to_xml(_call(svc.get, db, ref)), media_type="application/xml")


@router.get("/{ref}/print", response_class=HTMLResponse)
def report_print(ref: str, db: Session = Depends(get_db),
                 user: dict = Depends(current_user)) -> HTMLResponse:
    return HTMLResponse(svc.print_html(_call(svc.get, db, ref)),
                        headers={"Content-Security-Policy": _PRINT_CSP})
