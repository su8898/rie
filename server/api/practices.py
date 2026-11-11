"""The practice register, to read — any signed-in operator. Changes are ADMIN-only (/api/admin/practices)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .. import provider_registry_service as svc
from ..db import get_db
from .deps import current_user

router = APIRouter(prefix="/practices")


@router.get("")
def list_practices(q: str = "", status: str = "", page: int = Query(1, ge=1),
                   page_size: int = Query(25, ge=1, le=200), db: Session = Depends(get_db),
                   user: dict = Depends(current_user)) -> dict:
    return svc.list_practices(db, q=q, status=status, page=page, page_size=page_size)


@router.get("/summary")
def summary(db: Session = Depends(get_db), user: dict = Depends(current_user)) -> dict:
    return svc.summary(db)


@router.get("/{provider_id}")
def identity(provider_id: str, db: Session = Depends(get_db),
             user: dict = Depends(current_user)) -> dict:
    return svc.resolve_identity(db, provider_id)
