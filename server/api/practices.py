"""The practice register, to read — any signed-in operator. Changes are ADMIN-only (/api/admin/practices)."""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .. import party_intel_service, provider_registry_service as svc
from ..db import get_db
from .deps import current_user

router = APIRouter(prefix="/practices")


@router.get("")
def list_practices(q: str = "", status: str = "", discipline: str = "", setting: str = "",
                   practice_type: str = "", verified: Optional[bool] = None,
                   sort: Literal["number", "name", "discipline", "updated"] = "number",
                   direction: Literal["asc", "desc"] = "asc", page: int = Query(1, ge=1),
                   page_size: int = Query(25, ge=1, le=200), db: Session = Depends(get_db),
                   user: dict = Depends(current_user)) -> dict:
    return svc.list_practices(db, q=q, status=status, page=page, page_size=page_size,
                              discipline=discipline, setting=setting, practice_type=practice_type,
                              verified=verified, sort=sort, direction=direction)


@router.get("/summary")
def summary(db: Session = Depends(get_db), user: dict = Depends(current_user)) -> dict:
    return svc.summary(db)


@router.get("/unregistered")
def unregistered(q: str = "", page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=200),
                 db: Session = Depends(get_db), user: dict = Depends(current_user)) -> dict:
    """Practice numbers that have billed the Fund but are not in the register."""
    return svc.unregistered(db, q=q, page=page, page_size=page_size)


@router.get("/disciplines")
def disciplines(db: Session = Depends(get_db), user: dict = Depends(current_user)) -> list[str]:
    return svc.disciplines(db)


@router.get("/{provider_id}/activity")
def activity(provider_id: str, db: Session = Depends(get_db),
             user: dict = Depends(current_user)) -> dict:
    """Billing and payment totals, channel access and the change history for one practice."""
    return {**svc.activity(db, provider_id), "risk": _risk(db, provider_id)}


def _risk(db: Session, provider_id: str) -> Optional[dict]:
    row = next((p for p in party_intel_service.providers(db) if p["provider_id"] == provider_id), None)
    keys = ("score", "rating", "confidence", "n_claims", "red_rate", "flag_rate", "cohort", "value_percentile")
    return None if row is None else {k: row.get(k) for k in keys}


@router.get("/{provider_id}")
def identity(provider_id: str, db: Session = Depends(get_db),
             user: dict = Depends(current_user)) -> dict:
    return svc.resolve_identity(db, provider_id)
