"""Reference data an administrator maintains on screen (ADMIN only): diagnosis codes, the tariff
codes excluded from flat-rate pricing, and the code crosswalk. Reading diagnosis codes for a
lookup stays on /api/reference/icd10, open to any signed-in operator.
"""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import reference_admin_service as svc
from ..db import get_db
from .deps import require_role

router = APIRouter(prefix="/admin")
_admin = require_role("ADMIN")


# ── diagnosis codes ──
class IcdIn(BaseModel):
    code: str = Field(min_length=1, max_length=12)
    description: Optional[str] = Field(default=None, max_length=500)
    code3_desc: Optional[str] = Field(default=None, max_length=500)
    chapter_desc: Optional[str] = Field(default=None, max_length=500)
    valid_primary: Optional[bool] = None
    valid_clinical: Optional[bool] = None


class IcdImportIn(BaseModel):
    csv: str = Field(min_length=1, max_length=25_000_000)
    edition: str = Field(default="", max_length=120)


@router.get("/icd10")
def icd10(q: str = "", use: Literal["", "primary", "clinical", "heading"] = "",
          limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
          db: Session = Depends(get_db), user: dict = Depends(_admin)) -> dict:
    return svc.icd10_search(db, q, use, limit, offset)


@router.get("/icd10/summary")
def icd10_summary(db: Session = Depends(get_db), user: dict = Depends(_admin)) -> dict:
    return svc.icd10_summary(db)


@router.post("/icd10")
def icd10_upsert(body: IcdIn, db: Session = Depends(get_db), user: dict = Depends(_admin)) -> dict:
    return svc.icd10_upsert(db, user, body.model_dump(exclude_unset=True))


@router.post("/icd10/import")
def icd10_import(body: IcdImportIn, db: Session = Depends(get_db),
                 user: dict = Depends(_admin)) -> dict:
    return svc.icd10_import(db, user, body.csv, body.edition)


@router.delete("/icd10/{code:path}")
def icd10_remove(code: str, db: Session = Depends(get_db), user: dict = Depends(_admin)) -> dict:
    return svc.icd10_remove(db, user, code)


# ── flat-rate exclusions ──
class ExclusionIn(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    reason: str = Field(default="", max_length=300)


@router.get("/exclusions")
def exclusions(db: Session = Depends(get_db), user: dict = Depends(_admin)) -> list[dict]:
    return svc.list_exclusions(db)


@router.post("/exclusions")
def add_exclusion(body: ExclusionIn, db: Session = Depends(get_db),
                  user: dict = Depends(_admin)) -> dict:
    return svc.add_exclusion(db, user, body.code, body.reason)


@router.post("/exclusions/remove")
def remove_exclusion(body: ExclusionIn, db: Session = Depends(get_db),
                     user: dict = Depends(_admin)) -> dict:
    return svc.remove_exclusion(db, user, body.code, body.reason)


# ── code crosswalk ──
class CrosswalkIn(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    target_code: Optional[str] = Field(default=None, max_length=32)
    family: str = Field(default="", max_length=80)
    description: str = Field(default="", max_length=300)
    evidence: str = Field(default="", max_length=1000)


class CrosswalkStatusIn(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    status: Literal["CONFIRMED", "PROPOSED", "NEEDS_SME", "NO_RAF_EQUIVALENT"]
    reason: str = Field(default="", max_length=500)


class CrosswalkRemoveIn(BaseModel):
    code: str = Field(min_length=1, max_length=32)


@router.get("/crosswalk")
def crosswalk(db: Session = Depends(get_db), user: dict = Depends(_admin)) -> list[dict]:
    return svc.list_crosswalk(db)


@router.post("/crosswalk")
def upsert_crosswalk(body: CrosswalkIn, db: Session = Depends(get_db),
                     user: dict = Depends(_admin)) -> dict:
    return svc.upsert_crosswalk(db, user, body.model_dump())


@router.post("/crosswalk/status")
def crosswalk_status(body: CrosswalkStatusIn, db: Session = Depends(get_db),
                     user: dict = Depends(_admin)) -> dict:
    return svc.set_crosswalk_status(db, user, body.code, body.status, body.reason)


@router.post("/crosswalk/remove")
def remove_crosswalk(body: CrosswalkRemoveIn, db: Session = Depends(get_db),
                     user: dict = Depends(_admin)) -> dict:
    return svc.remove_crosswalk(db, user, body.code)
