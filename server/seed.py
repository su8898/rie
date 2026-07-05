"""Create tables and seed dev users + statutory config; demo pricing only when no real
reference data is loaded (so `db/load_reference.py` is not overwritten). Idempotent."""
from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import models
from .db import Base, SessionLocal, engine
from .security import hash_password

_USERS = [("admin", "ADMIN"), ("handler", "HANDLER"), ("medical", "MEDICAL_OFFICER"),
          ("investigator", "INVESTIGATOR"), ("legal", "LEGAL")]


def _empty(db: Session, model) -> bool:
    return db.scalar(select(func.count()).select_from(model)) == 0


def seed_users(db: Session) -> None:
    if _empty(db, models.AppUser):
        for uname, role in _USERS:
            db.add(models.AppUser(username=uname, password_hash=hash_password(uname), role=role))


def seed_statutory(db: Session) -> None:
    """Statutory config — caps (s17(4)(c)) + pre-auth classes. Always present, not demo pricing."""
    if _empty(db, models.RefCap):
        db.add_all([
            models.RefCap(effective_from=date(2015, 1, 1), annual_cap=160000.0),
            models.RefCap(effective_from=date(2026, 1, 31), annual_cap=378581.0),  # RAF v Sweatman
        ])
    if _empty(db, models.RefPreauth):
        db.add(models.RefPreauth(code="0500"))              # placeholder pre-auth class (ruleset config)


def seed_demo_pricing(db: Session) -> None:
    """Small demo reference prices — ONLY when no real reference data (ref_rpl) is loaded."""
    if not _empty(db, models.RefRpl):
        return
    # TARIFF-family codes stored NORMALISED (zero-stripped), matching db/load_reference.py.
    db.add_all([
        models.RefRpl(code="190", gp=500.0, spec=700.0),
        models.RefRpl(code="23", gp=100.0, spec=None),
        models.RefRpl(code="100", gp=200.0, spec=None),
        models.RefNegotiated(kind="TARIFF", code="55", rate=400.0),
        models.RefRaf2022(code="200", rate=300.0),
        models.RefRaf2022(code="300", rate=50.0),
        models.RefEmpirical(kind="TARIFF", code="999", median=250.0),
        models.RefEmpirical(kind="TARIFF", code="300", median=300.0),
        models.RefEmpirical(kind="NAPPI", code="888", median=90.0),
        models.RefNappiSep(nappi_code="700101", sep=88.40),
        models.RefNonBench(code="0011"),
    ])


def seed(db: Session) -> None:
    seed_users(db)
    seed_statutory(db)
    seed_demo_pricing(db)
    db.commit()


def init_db() -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed(db)
