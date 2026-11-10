"""Dated reference rates — browse the rate in force on a date, its versions and the change trail
(any signed-in operator), and maintain them (ADMIN): add / supersede, percentage increase (one or
bulk), correct, retire, CSV import and export.

Pricing follows from this data alone: the engine pays each line at the version in force on its
service date, so a change here is reference data, never a code deploy.
"""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import rates_service as svc
from ..db import get_db
from .deps import current_user, require_role

router = APIRouter(prefix="/rates")
_admin = require_role("ADMIN")

Source = Literal["RPL", "NEGOTIATED", "SEP"]
Kind = Literal["TARIFF", "NAPPI"]


class KeyIn(BaseModel):
    source: Source
    kind: Optional[Kind] = None
    code: str = Field(min_length=1, max_length=32)
    discipline: str = Field(default="", max_length=64)


class VersionIn(KeyIn):
    rate: float = Field(ge=0, le=1_000_000_000)
    effective_from: date
    note: str = Field(default="", max_length=500)


class IncreaseIn(KeyIn):
    pct: float = Field(gt=-100, le=1000)
    effective_from: date


class BulkIncreaseIn(BaseModel):
    source: Literal["RPL", "NEGOTIATED"]
    pct: float = Field(gt=-100, le=1000)
    effective_from: date
    q: str = Field(default="", max_length=32)
    discipline: str = Field(default="", max_length=64)


class AdjustIn(BaseModel):
    rate: float = Field(ge=0, le=1_000_000_000)
    note: str = Field(default="", max_length=500)


class RetireIn(BaseModel):
    effective_to: date
    note: str = Field(default="", max_length=500)


class ImportIn(BaseModel):
    csv: str = Field(min_length=1, max_length=5_000_000)
    source: Source = "RPL"


# ── reads (any signed-in operator) ──
@router.get("")
def current(source: Source = "RPL", q: str = Query("", max_length=32),
            discipline: str = Query("", max_length=64), on: Optional[date] = None,
            limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
            db: Session = Depends(get_db), user: dict = Depends(current_user)) -> dict:
    return svc.list_current(db, source, q, discipline, on, limit, offset)


@router.get("/summary")
def summary(db: Session = Depends(get_db), user: dict = Depends(current_user)) -> dict:
    return svc.summary(db)


@router.get("/versions")
def versions(source: Source, code: str = Query(min_length=1, max_length=32),
             kind: Optional[Kind] = None, discipline: str = Query("", max_length=64),
             db: Session = Depends(get_db), user: dict = Depends(current_user)) -> list[dict]:
    return svc.versions(db, source, kind, code, discipline)


@router.get("/log")
def log(limit: int = Query(100, ge=1, le=500), source: str = Query("", max_length=16),
        code: str = Query("", max_length=32),
        db: Session = Depends(get_db), user: dict = Depends(current_user)) -> list[dict]:
    return svc.log(db, limit, source, code)


@router.get("/export", response_class=PlainTextResponse)
def export(source: Source = "RPL", on: Optional[date] = None,
           db: Session = Depends(get_db), user: dict = Depends(current_user)) -> PlainTextResponse:
    return PlainTextResponse(
        svc.export_csv(db, source, on), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="rates-{source.lower()}.csv"'})


# ── maintenance (ADMIN) ──
@router.post("")
def add_or_supersede(body: VersionIn, db: Session = Depends(get_db),
                     user: dict = Depends(_admin)) -> dict:
    return svc.add_or_supersede(db, user, body.source, body.kind, body.code, body.discipline,
                                body.rate, body.effective_from, body.note)


@router.post("/increase")
def increase(body: IncreaseIn, db: Session = Depends(get_db), user: dict = Depends(_admin)) -> dict:
    return svc.increase(db, user, body.source, body.kind, body.code, body.discipline, body.pct,
                        body.effective_from)


@router.post("/bulk-increase")
def bulk_increase(body: BulkIncreaseIn, db: Session = Depends(get_db),
                  user: dict = Depends(_admin)) -> dict:
    return svc.bulk_increase(db, user, body.source, body.pct, body.effective_from, body.q,
                             body.discipline)


@router.post("/import")
def import_csv(body: ImportIn, db: Session = Depends(get_db), user: dict = Depends(_admin)) -> dict:
    return svc.import_csv(db, user, body.csv, body.source)


@router.post("/{rate_id}/adjust")
def adjust(rate_id: int, body: AdjustIn, db: Session = Depends(get_db),
           user: dict = Depends(_admin)) -> dict:
    return svc.adjust(db, user, rate_id, body.rate, body.note)


@router.post("/{rate_id}/retire")
def retire(rate_id: int, body: RetireIn, db: Session = Depends(get_db),
           user: dict = Depends(_admin)) -> dict:
    return svc.retire(db, user, rate_id, body.effective_to, body.note)
