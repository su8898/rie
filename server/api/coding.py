"""Coding intelligence (SPECIFICATION §6) — code aggregation, overage, condition bands, targets."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .. import coding_service as svc
from ..db import get_db
from .deps import current_user

router = APIRouter(prefix="/coding")


@router.get("/codes")
def codes(kind: str | None = None, limit: int = Query(200, ge=1, le=1000),
          db: Session = Depends(get_db), user: dict = Depends(current_user)) -> list[dict]:
    return svc.code_aggregation(db, kind=kind, limit=limit)


@router.get("/negotiation-targets")
def negotiation_targets(limit: int = Query(50, ge=1, le=500), db: Session = Depends(get_db),
                        user: dict = Depends(current_user)) -> list[dict]:
    return svc.negotiation_targets(db, limit=limit)


@router.get("/drift")
def drift(min_months: int = Query(svc.DRIFT_MIN_MONTHS, ge=2, le=60),
          min_lines: int = Query(svc.DRIFT_MIN_LINES, ge=1, le=1000),
          limit: int = Query(40, ge=1, le=500), db: Session = Depends(get_db),
          user: dict = Depends(current_user)) -> dict:
    return svc.price_drift(db, min_months=min_months, min_lines=min_lines, limit=limit)


@router.get("/conditions")
def conditions(db: Session = Depends(get_db), user: dict = Depends(current_user)) -> list[dict]:
    return svc.condition_bands(db)


@router.get("/estimate")
def estimate(injury_class: str, amount: float, db: Session = Depends(get_db),
             user: dict = Depends(current_user)) -> dict:
    return svc.estimate(db, injury_class, amount)
