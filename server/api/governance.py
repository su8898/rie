"""Precision / recall governance — the close-the-loop feedback layer (domain-logic §11).

Substantiation (precision) per signal with Wilson intervals, the SHADOW->ADVISORY->SCORED
promotion action list, the recall QA sample + estimate, and the labels export (JSON + CSV).
"""
from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from .. import precision_service as svc
from ..db import get_db
from .deps import current_user

router = APIRouter(prefix="/governance")


@router.get("/precision")
def precision(db: Session = Depends(get_db), user: dict = Depends(current_user)) -> list[dict]:
    return svc.precision_by_signal(db)


@router.get("/promotions")
def promotions(db: Session = Depends(get_db), user: dict = Depends(current_user)) -> list[dict]:
    return svc.promotions(db)


@router.get("/recall/sample")
def recall_sample(n: int = Query(20, ge=1, le=500), db: Session = Depends(get_db),
                  user: dict = Depends(current_user)) -> dict:
    return svc.recall_qa_sample(db, n=n)


@router.get("/recall")
def recall(db: Session = Depends(get_db), user: dict = Depends(current_user)) -> dict:
    return svc.recall_estimate(db)


@router.post("/recall/draw")
def recall_draw(n: int = Query(30, ge=1, le=200), db: Session = Depends(get_db),
                user: dict = Depends(current_user)) -> dict:
    """Open blind-QA REVIEW cases from the recall sample (§11 close-the-loop workflow)."""
    return svc.draw_recall_qa(db, user, n=n)


@router.get("/labels")
def labels(db: Session = Depends(get_db), user: dict = Depends(current_user)) -> list[dict]:
    return svc.labels_export(db)


@router.get("/labels.csv")
def labels_csv(db: Session = Depends(get_db), user: dict = Depends(current_user)) -> PlainTextResponse:
    rows = svc.labels_export(db)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["claim_id", "verdict", "label", "lane", "case_id"])
    writer.writeheader()
    writer.writerows(rows)
    return PlainTextResponse(buf.getvalue(), media_type="text/csv")
