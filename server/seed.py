"""Create tables and seed dev users + statutory config; demo pricing only when no real
reference data is loaded (so `db/load_reference.py` is not overwritten). Idempotent."""
from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import models
from .config import BOOTSTRAP_ADMIN_PASSWORD, SEED_DEV_USERS
from .db import Base, SessionLocal, engine
from .security import hash_password

# Dev logins (username == password). `treasury` is the second ADMIN the payment flow needs:
# assembler, approver and payer must be three different people (§8e segregation of duties).
_USERS = [("admin", "ADMIN"), ("treasury", "ADMIN"), ("handler", "HANDLER"),
          ("medical", "MEDICAL_OFFICER"), ("investigator", "INVESTIGATOR"), ("legal", "LEGAL")]


def _empty(db: Session, model) -> bool:
    return db.scalar(select(func.count()).select_from(model)) == 0


def seed_users(db: Session) -> None:
    """Dev/test: the username==password dev logins. Production: never — bootstrap ONE admin from
    RIE_BOOTSTRAP_ADMIN_PASSWORD when the table is empty, otherwise leave users alone."""
    if SEED_DEV_USERS:                                  # dev/test: ensure every dev login exists
        have = set(db.scalars(select(models.AppUser.username)))
        for uname, role in _USERS:
            if uname not in have:
                db.add(models.AppUser(username=uname, password_hash=hash_password(uname), role=role))
        return
    if not _empty(db, models.AppUser):
        return
    if BOOTSTRAP_ADMIN_PASSWORD:
        db.add(models.AppUser(username="admin", password_hash=hash_password(BOOTSTRAP_ADMIN_PASSWORD),
                              role="ADMIN"))


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
    # TARIFF-family codes stored NORMALISED (zero-stripped), matching db/load_reference.py;
    # RPL rates are per-discipline (code 190 differs GP vs SPECIALIST).
    db.add_all([
        models.RefRpl(code="190", discipline="GP", rate=500.0),
        models.RefRpl(code="190", discipline="SPECIALIST", rate=700.0),
        models.RefRpl(code="23", discipline="GP", rate=100.0),
        models.RefRpl(code="100", discipline="GP", rate=200.0),
        models.RefNegotiated(kind="TARIFF", code="55", rate=400.0),
        models.RefRaf2022(code="200", rate=300.0),
        models.RefRaf2022(code="300", rate=50.0),
        models.RefEmpirical(kind="TARIFF", code="999", median=250.0),
        models.RefEmpirical(kind="TARIFF", code="300", median=300.0),
        models.RefEmpirical(kind="NAPPI", code="888", median=90.0),
        models.RefNappiSep(nappi_code="700101", sep=88.40),
        models.RefNonBench(code="0011"),
    ])


# Representative SA headline CPI index (annual, arbitrary base 2014=100) — for inflation-adjusting
# comparable awards to current rand (§5d). A real deployment loads Stats SA figures.
_CPI = {2008: 72.0, 2009: 77.0, 2010: 80.0, 2011: 84.0, 2012: 89.0, 2013: 94.0, 2014: 100.0,
        2015: 105.0, 2016: 112.0, 2017: 118.0, 2018: 124.0, 2019: 129.0, 2020: 133.0,
        2021: 139.0, 2022: 148.0, 2023: 157.0, 2024: 165.0, 2025: 172.0, 2026: 180.0}

# Representative general-damages authorities (injury_class, severity, award-year, award-rand).
# Illustrative seed only — cited to the standard SA quantum source; a real deployment loads
# LEGAL-curated authorities. Bands are COMPUTED from these (CPI-adjusted p25–p75), never hand-set.
# TBI/PARAPLEGIA/QUADRIPLEGIA/ORTHOPAEDIC_FEMUR have >=5 (robust band); AMPUTATION/FACIAL <5 (small-n).
_AWARDS = [
    ("TBI", "SEVERE", 2012, 1_400_000), ("TBI", "SEVERE", 2014, 1_600_000),
    ("TBI", "SEVERE", 2016, 1_800_000), ("TBI", "SEVERE", 2018, 1_900_000),
    ("TBI", "SEVERE", 2020, 2_000_000), ("TBI", "SEVERE", 2022, 2_200_000),
    ("TBI", "MODERATE", 2013, 600_000), ("TBI", "MODERATE", 2015, 700_000),
    ("TBI", "MODERATE", 2017, 800_000), ("TBI", "MODERATE", 2019, 850_000),
    ("TBI", "MODERATE", 2021, 950_000),
    ("PARAPLEGIA", "SEVERE", 2011, 2_000_000), ("PARAPLEGIA", "SEVERE", 2014, 2_200_000),
    ("PARAPLEGIA", "SEVERE", 2016, 2_500_000), ("PARAPLEGIA", "SEVERE", 2018, 2_700_000),
    ("PARAPLEGIA", "SEVERE", 2020, 2_900_000), ("PARAPLEGIA", "SEVERE", 2023, 3_200_000),
    ("QUADRIPLEGIA", "SEVERE", 2012, 2_800_000), ("QUADRIPLEGIA", "SEVERE", 2015, 3_200_000),
    ("QUADRIPLEGIA", "SEVERE", 2018, 3_600_000), ("QUADRIPLEGIA", "SEVERE", 2020, 3_900_000),
    ("QUADRIPLEGIA", "SEVERE", 2022, 4_200_000),
    ("ORTHOPAEDIC_FEMUR", "MODERATE", 2014, 350_000), ("ORTHOPAEDIC_FEMUR", "MODERATE", 2016, 400_000),
    ("ORTHOPAEDIC_FEMUR", "MODERATE", 2018, 450_000), ("ORTHOPAEDIC_FEMUR", "MODERATE", 2020, 500_000),
    ("ORTHOPAEDIC_FEMUR", "MODERATE", 2022, 580_000),
    ("AMPUTATION_LOWER_LIMB", "SEVERE", 2015, 900_000),
    ("AMPUTATION_LOWER_LIMB", "SEVERE", 2018, 1_100_000),
    ("AMPUTATION_LOWER_LIMB", "SEVERE", 2021, 1_300_000),
    ("FACIAL_DISFIGUREMENT", "MODERATE", 2016, 280_000),
    ("FACIAL_DISFIGUREMENT", "MODERATE", 2018, 320_000),
    ("FACIAL_DISFIGUREMENT", "MODERATE", 2020, 380_000),
    ("FACIAL_DISFIGUREMENT", "MODERATE", 2022, 450_000),
]


def seed_awards(db: Session) -> None:
    """CPI index + representative comparable-awards curation (§5d) — only when empty."""
    if _empty(db, models.RefCpi):
        db.add_all([models.RefCpi(year=y, index=i) for y, i in _CPI.items()])
    if _empty(db, models.RefComparableAward):
        db.add_all([models.RefComparableAward(
            injury_class=ic, severity_tier=sv, award_rand=float(rand), award_date=date(yr, 6, 30),
            citation=f"Koch Quantum Yearbook {yr}", court="High Court",
            notes="representative seed — replace with LEGAL-curated authority")
            for ic, sv, yr, rand in _AWARDS])


def seed(db: Session) -> None:
    from .reference_admin_service import seed_crosswalk   # imported here: it imports the admin layer

    seed_users(db)
    seed_statutory(db)
    seed_demo_pricing(db)
    seed_awards(db)
    seed_crosswalk(db)
    db.commit()


def init_db() -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed(db)
