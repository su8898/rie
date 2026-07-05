"""Leakage — portfolio and per-claim payment-integrity decomposition."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..leakage_service import claim_leakage, portfolio_leakage
from .deps import current_user

router = APIRouter(prefix="/leakage")


@router.get("")
def portfolio(db: Session = Depends(get_db), user: dict = Depends(current_user)) -> dict:
    return portfolio_leakage(db)


@router.get("/{claim_id}")
def per_claim(claim_id: str, db: Session = Depends(get_db),
              user: dict = Depends(current_user)) -> dict:
    return claim_leakage(db, claim_id)
