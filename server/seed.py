"""Create tables and seed dev users + reference data (idempotent)."""
from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import models
from .db import Base, SessionLocal, engine
from .security import hash_password

_USERS = [("admin", "ADMIN"), ("handler", "HANDLER"), ("medical", "MEDICAL_OFFICER"),
          ("investigator", "INVESTIGATOR"), ("legal", "LEGAL")]


def seed(db: Session) -> None:
    if db.scalar(select(func.count()).select_from(models.AppUser)) == 0:
        for uname, role in _USERS:
            db.add(models.AppUser(username=uname, password_hash=hash_password(uname), role=role))

    if db.scalar(select(func.count()).select_from(models.RefRpl)) == 0:
        db.add_all([
            models.RefRpl(code="0190", gp=500.0, spec=700.0),
            models.RefRpl(code="0023", gp=100.0, spec=None),
            models.RefRpl(code="0100", gp=200.0, spec=None),
            models.RefNegotiated(kind="TARIFF", code="0055", rate=400.0),
            models.RefRaf2022(code="0200", rate=300.0),
            models.RefRaf2022(code="0300", rate=50.0),
            models.RefEmpirical(kind="TARIFF", code="0999", median=250.0),
            models.RefEmpirical(kind="TARIFF", code="0300", median=300.0),
            models.RefEmpirical(kind="NAPPI", code="888", median=90.0),
            models.RefNappiSep(nappi_code="700101", sep=88.40),
            models.RefNonBench(code="0011"),
            models.RefCap(effective_from=date(2015, 1, 1), annual_cap=160000.0),
            models.RefCap(effective_from=date(2026, 1, 31), annual_cap=378581.0),
            models.RefPreauth(code="0500"),
        ])
    db.commit()


def init_db() -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed(db)
