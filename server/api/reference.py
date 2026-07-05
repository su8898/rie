"""Reference-data lookups — browse the loaded tariffs / NAPPI / ICD-10 + edition provenance.

Always limited (the NAPPI table is ~540k rows): pass ?code= for an exact hit or ?q= for a
prefix/description search.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import models
from ..awards_service import award_band, injury_classes
from ..db import get_db
from ..reference_data import _norm
from .deps import current_user

router = APIRouter(prefix="/reference")


@router.get("/editions")
def editions(db: Session = Depends(get_db), user: dict = Depends(current_user)) -> list[dict]:
    return [{"kind": e.kind, "version": e.version, "n": e.n, "synced_at": e.synced_at}
            for e in db.scalars(select(models.RefEdition))]


@router.get("/disciplines")
def disciplines(db: Session = Depends(get_db), user: dict = Depends(current_user)) -> list[str]:
    """Distinct provider disciplines present in the loaded tariff schedules (for the submit UI)."""
    return list(db.scalars(select(models.RefRpl.discipline).distinct()
                           .order_by(models.RefRpl.discipline)))


@router.get("/tariffs")
def tariffs(code: str | None = None, q: str | None = None, limit: int = Query(50, le=200),
            db: Session = Depends(get_db), user: dict = Depends(current_user)) -> list[dict]:
    stmt = select(models.RefRpl)
    if code:
        stmt = stmt.where(models.RefRpl.code == _norm(code))
    elif q:
        stmt = stmt.where(models.RefRpl.code.like(f"{_norm(q)}%"))
    return [{"code": r.code, "discipline": r.discipline, "rate": r.rate}
            for r in db.scalars(stmt.order_by(models.RefRpl.code, models.RefRpl.discipline)
                                .limit(limit))]


@router.get("/nappi")
def nappi(code: str | None = None, q: str | None = None, limit: int = Query(50, le=200),
          db: Session = Depends(get_db), user: dict = Depends(current_user)) -> list[dict]:
    stmt = select(models.RefNappiSep)
    if code:
        stmt = stmt.where(models.RefNappiSep.nappi_code == code)
    elif q:
        stmt = stmt.where(models.RefNappiSep.nappi_code.like(f"{q}%"))
    return [{"nappi_code": r.nappi_code, "sep": r.sep}
            for r in db.scalars(stmt.order_by(models.RefNappiSep.nappi_code).limit(limit))]


@router.get("/awards/classes")
def award_classes(db: Session = Depends(get_db), user: dict = Depends(current_user)) -> list[dict]:
    """Distinct injury classes + their severity tiers in the comparable-awards store (§5d)."""
    return injury_classes(db)


@router.get("/awards")
def awards(injury_class: str, severity: str | None = None,
           db: Session = Depends(get_db), user: dict = Depends(current_user)) -> dict:
    """Computed general-damages band (CPI-adjusted p25–p75, small-n-guarded) + the authorities."""
    return award_band(db, injury_class, severity)


@router.get("/icd10")
def icd10(code: str | None = None, q: str | None = None, limit: int = Query(50, le=200),
          db: Session = Depends(get_db), user: dict = Depends(current_user)) -> list[dict]:
    stmt = select(models.RefIcd10)
    if code:
        stmt = stmt.where(models.RefIcd10.code == code)
    elif q:
        stmt = stmt.where(or_(models.RefIcd10.code.like(f"{q}%"),
                             models.RefIcd10.description.like(f"%{q}%")))
    return [{"code": r.code, "description": r.description, "chapter": r.chapter_desc,
             "valid_primary": r.valid_primary}
            for r in db.scalars(stmt.order_by(models.RefIcd10.code).limit(limit))]
