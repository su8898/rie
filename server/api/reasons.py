"""The reason-code catalogue — every code with maturity, basis, points, and live signal mode."""
from __future__ import annotations

from fastapi import APIRouter, Depends

import engine

from .deps import current_user

router = APIRouter(prefix="/reasons")


@router.get("")
def catalogue(user: dict = Depends(current_user)) -> list[dict]:
    out = []
    for code, meta in engine.R.items():
        out.append({
            "code": code, "category": meta.category.name, "hard": meta.hard,
            "points": meta.points, "maturity": meta.maturity.name,
            "endogenous": meta.endogenous, "basis": meta.basis,
            "mode": engine.MODE[code].name,
        })
    return out
