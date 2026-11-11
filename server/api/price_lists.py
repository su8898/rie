"""Price lists — whole tariff editions held as reference data. Any signed-in operator can browse
a list, search its entries and export it; an ADMIN creates lists, loads and edits the entries of a
draft, publishes, retires, issues a new edition and changes a list's legal standing.

A price list prices nothing by being here: the engine reads the dated rate store (/api/rates).
"""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import price_list_service as svc
from ..db import get_db
from .deps import current_user, require_role

router = APIRouter(prefix="/price-lists")
_admin = require_role("ADMIN")

Legal = Literal["ENFORCEABLE", "ACCEPTED", "INTERDICTED"]


class ListIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    edition: str = Field(default="", max_length=160)
    source: str = Field(default="", max_length=500)
    legal_status: Legal = "ACCEPTED"
    status_note: str = Field(default="", max_length=500)
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None
    notes: str = Field(default="", max_length=4000)


class ListPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=160)
    edition: Optional[str] = Field(default=None, max_length=160)
    source: Optional[str] = Field(default=None, max_length=500)
    legal_status: Optional[Legal] = None
    status_note: Optional[str] = Field(default=None, max_length=500)
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None
    notes: Optional[str] = Field(default=None, max_length=4000)


class LegalIn(BaseModel):
    legal_status: Legal
    reason: str = Field(min_length=1, max_length=500)


class FactorIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    value: float = Field(ge=0, le=1_000_000_000)


class FactorsIn(BaseModel):
    factors: list[FactorIn] = Field(max_length=50)


class RetireIn(BaseModel):
    effective_to: Optional[date] = None
    note: str = Field(default="", max_length=500)


class CopyIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    edition: str = Field(default="", max_length=160)


class EntryIn(BaseModel):
    discipline: str = Field(default="", max_length=120)
    code: str = Field(default="", max_length=40)
    alt_code: str = Field(default="", max_length=40)
    price_column: str = Field(default="standard", max_length=80)
    description: str = Field(default="", max_length=4000)
    units: Optional[float] = Field(default=None, ge=0, le=1_000_000_000)
    units_suffix: str = Field(default="", max_length=8)
    value_rand: Optional[float] = Field(default=None, ge=0, le=1_000_000_000)
    unit_of_issue: str = Field(default="", max_length=20)
    source_page: str = Field(default="", max_length=20)
    note: str = Field(default="", max_length=500)


class ImportIn(BaseModel):
    csv: str = Field(min_length=1, max_length=25_000_000)
    mode: Literal["append", "replace"] = "append"


# ── reads (any signed-in operator) ──
@router.get("")
def list_lists(db: Session = Depends(get_db), user: dict = Depends(current_user)) -> list[dict]:
    return svc.list_lists(db)


@router.get("/{list_id}")
def get_list(list_id: int, db: Session = Depends(get_db),
             user: dict = Depends(current_user)) -> dict:
    return svc.get(db, list_id)


@router.get("/{list_id}/entries")
def entries(list_id: int, q: str = "", discipline: str = "", column: str = "",
            priced: Literal["", "value", "units_only", "none"] = "",
            limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
            db: Session = Depends(get_db), user: dict = Depends(current_user)) -> dict:
    return svc.entries(db, list_id, q, discipline, column, priced, limit, offset)


@router.get("/{list_id}/export", response_class=PlainTextResponse)
def export(list_id: int, db: Session = Depends(get_db),
           user: dict = Depends(current_user)) -> PlainTextResponse:
    return PlainTextResponse(
        svc.export_csv(db, list_id), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="price-list-{list_id}.csv"'})


@router.get("/{list_id}/history")
def history(list_id: int, db: Session = Depends(get_db),
            user: dict = Depends(current_user)) -> list[dict]:
    return svc.history(db, list_id)


# ── maintenance (ADMIN) ──
@router.post("")
def create(body: ListIn, db: Session = Depends(get_db), user: dict = Depends(_admin)) -> dict:
    return svc.create(db, user, body.model_dump())


@router.patch("/{list_id}")
def update(list_id: int, body: ListPatch, db: Session = Depends(get_db),
           user: dict = Depends(_admin)) -> dict:
    return svc.update(db, user, list_id, body.model_dump(exclude_unset=True))


@router.post("/{list_id}/legal-status")
def legal_status(list_id: int, body: LegalIn, db: Session = Depends(get_db),
                 user: dict = Depends(_admin)) -> dict:
    return svc.set_legal_status(db, user, list_id, body.legal_status, body.reason)


@router.put("/{list_id}/factors")
def factors(list_id: int, body: FactorsIn, db: Session = Depends(get_db),
            user: dict = Depends(_admin)) -> dict:
    return svc.set_factors(db, user, list_id, [f.model_dump() for f in body.factors])


@router.post("/{list_id}/publish")
def publish(list_id: int, db: Session = Depends(get_db), user: dict = Depends(_admin)) -> dict:
    return svc.publish(db, user, list_id)


@router.post("/{list_id}/retire")
def retire(list_id: int, body: RetireIn, db: Session = Depends(get_db),
           user: dict = Depends(_admin)) -> dict:
    return svc.retire(db, user, list_id, body.effective_to, body.note)


@router.post("/{list_id}/copy")
def copy(list_id: int, body: CopyIn, db: Session = Depends(get_db),
         user: dict = Depends(_admin)) -> dict:
    return svc.copy(db, user, list_id, body.name, body.edition)


@router.delete("/{list_id}")
def remove(list_id: int, db: Session = Depends(get_db), user: dict = Depends(_admin)) -> dict:
    return svc.remove(db, user, list_id)


@router.post("/{list_id}/entries")
def add_entry(list_id: int, body: EntryIn, db: Session = Depends(get_db),
              user: dict = Depends(_admin)) -> dict:
    return svc.add_entry(db, user, list_id, body.model_dump())


@router.patch("/{list_id}/entries/{entry_id}")
def update_entry(list_id: int, entry_id: int, body: EntryIn, db: Session = Depends(get_db),
                 user: dict = Depends(_admin)) -> dict:
    return svc.update_entry(db, user, list_id, entry_id, body.model_dump(exclude_unset=True))


@router.delete("/{list_id}/entries/{entry_id}")
def delete_entry(list_id: int, entry_id: int, db: Session = Depends(get_db),
                 user: dict = Depends(_admin)) -> dict:
    return svc.delete_entry(db, user, list_id, entry_id)


@router.post("/{list_id}/import")
def import_csv(list_id: int, body: ImportIn, db: Session = Depends(get_db),
               user: dict = Depends(_admin)) -> dict:
    return svc.import_csv(db, user, list_id, body.csv, body.mode)
