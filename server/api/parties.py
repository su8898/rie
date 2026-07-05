"""Party intelligence — provider / attorney / claimant cohort scoring, fairness, risk sweep."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .. import party_intel_service as svc
from ..db import get_db
from .deps import current_user

router = APIRouter(prefix="/parties")


@router.get("/providers")
def providers(db: Session = Depends(get_db), user: dict = Depends(current_user)) -> list[dict]:
    return svc.providers(db)


@router.get("/attorneys")
def attorneys(db: Session = Depends(get_db), user: dict = Depends(current_user)) -> list[dict]:
    return svc.attorneys(db)


@router.get("/claimants")
def claimants(db: Session = Depends(get_db), user: dict = Depends(current_user)) -> list[dict]:
    return svc.claimants(db)


@router.get("/fairness")
def fairness(db: Session = Depends(get_db), user: dict = Depends(current_user)) -> dict:
    return svc.fairness(db)


@router.get("/risk-sweep")
def risk_sweep(threshold: float = Query(55.0, ge=0, le=100),
               db: Session = Depends(get_db), user: dict = Depends(current_user)) -> dict:
    return svc.risk_sweep(db, threshold=threshold)
