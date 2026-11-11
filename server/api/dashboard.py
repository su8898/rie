"""Portfolio snapshot — band/disposition mix, exposure, eligibility."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from .. import work_query
from ..db import get_db
from ..models import Determination, latest_determination_ids
from .deps import current_user

router = APIRouter(prefix="/dashboard")


@router.get("")
def dashboard(db: Session = Depends(get_db), user: dict = Depends(current_user)) -> dict:
    """Portfolio snapshot over each claim's LATEST determination only — a rescore supersedes the
    earlier verdict, so superseded rows never inflate counts or rand totals."""
    latest = Determination.id.in_(latest_determination_ids())
    bands = dict(db.execute(
        select(Determination.band, func.count()).where(latest).group_by(Determination.band)).all())
    disps = dict(db.execute(
        select(Determination.disposition, func.count()).where(latest)
        .group_by(Determination.disposition)).all())
    total, net, medical, review = db.execute(select(
        func.count(Determination.id),
        func.coalesce(func.sum(Determination.net_payable), 0.0),
        func.coalesce(func.sum(Determination.medical_payable), 0.0),
        func.coalesce(func.sum(case((Determination.needs_review.is_(True), 1), else_=0)), 0),
    ).where(latest)).one()
    eligible = db.scalar(select(func.count()).select_from(Determination)
                         .where(latest, Determination.eligible_to_pay.is_(True)))
    return {
        "determinations": total,
        "by_band": {"GREEN": bands.get("GREEN", 0), "AMBER": bands.get("AMBER", 0), "RED": bands.get("RED", 0)},
        "by_disposition": disps,
        "eligible_to_pay": eligible,
        "needs_review": int(review),
        "net_payable_total": round(float(net), 2),
        "medical_payable_total": round(float(medical), 2),
    }


@router.get("/work")
def work(db: Session = Depends(get_db), user: dict = Depends(current_user)) -> dict:
    """What is waiting in each queue, for the signed-in user."""
    return work_query.work_summary(db, user)
