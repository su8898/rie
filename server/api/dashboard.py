"""Portfolio snapshot — band/disposition mix, exposure, eligibility."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Determination
from .deps import current_user

router = APIRouter(prefix="/dashboard")


@router.get("")
def dashboard(db: Session = Depends(get_db), user: dict = Depends(current_user)) -> dict:
    bands = dict(db.execute(
        select(Determination.band, func.count()).group_by(Determination.band)).all())
    disps = dict(db.execute(
        select(Determination.disposition, func.count()).group_by(Determination.disposition)).all())
    total, net, medical = db.execute(select(
        func.count(Determination.id),
        func.coalesce(func.sum(Determination.net_payable), 0.0),
        func.coalesce(func.sum(Determination.medical_payable), 0.0),
    )).one()
    eligible = db.scalar(select(func.count()).select_from(Determination)
                         .where(Determination.eligible_to_pay.is_(True)))
    return {
        "determinations": total,
        "by_band": {"GREEN": bands.get("GREEN", 0), "AMBER": bands.get("AMBER", 0), "RED": bands.get("RED", 0)},
        "by_disposition": disps,
        "eligible_to_pay": eligible,
        "net_payable_total": round(float(net), 2),
        "medical_payable_total": round(float(medical), 2),
    }
