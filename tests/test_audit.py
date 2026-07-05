"""Audit / clawback recovery — isolated in-memory DB, deterministic.

Models the realistic case: a provider's paid (clean) claims get swept for clawback once the
provider is found high-risk from its *other* (flagged, unpaid) claims.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from server import audit_service as aud, models, party_intel_service as pi, payments_service as pay
from server import statemachine as sm
from server.db import Base
from server.pipeline_service import assess_and_store
from server.seed import seed

H = {"username": "handler", "role": "HANDLER"}
A = {"username": "admin", "role": "ADMIN"}
I = {"username": "inv", "role": "INVESTIGATOR"}


def _session():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    db = sessionmaker(bind=eng)()
    seed(db)
    return db


def _supplier(cid, party, cas, provider, dx="S72", dx_regions=None):
    p = {"claim_id": cid, "claim_type": "SUPPLIER", "party_token": party,
         "accident_date": "2026-02-01", "lodged_on": "2026-03-01", "case_number_raw": cas,
         "today": "2026-07-05", "payee_verified": True,
         "documents": {"RAF2": True, "OAR": True, "INVOICES": True, "BANK": True},
         "lines": [{"kind": "TARIFF", "code": "0190", "qty": 1, "amount": 500.0,
                    "service_date": "2026-03-01", "provider_id": provider, "dx": dx}]}
    if dx_regions:
        p["accident_dx_regions"] = dx_regions
    return p


def _seed_bad_provider(db):
    for i in range(2):                                   # flagged (dx-mismatch, FRAUD, unpaid)
        assess_and_store(db, _supplier(f"R_f{i}", f"P_f{i}", f"CAS 960{i}/02/2026", "PR_BAD",
                                       dx="K35", dx_regions=["S72"]))
    clean = []
    for i in range(3):                                   # clean, will be PAID
        cid = f"R_c{i}"
        assess_and_store(db, _supplier(cid, f"P_c{i}", f"CAS 961{i}/02/2026", "PR_BAD"))
        clean.append(cid)
    b = pay.create_batch(db, H)
    for cid in clean:
        pay.add_instruction(db, b.id, cid, "SUPPLIER", None, H)
    pay.approve(db, b.id, A)
    pay.pay(db, b.id, A)
    return clean


def test_provider_is_high_risk():
    db = _session()
    _seed_bad_provider(db)
    prov = {p["provider_id"]: p for p in pi.providers(db)}
    assert prov["PR_BAD"]["score"] >= 20                 # WATCH+ from the flagged claims


def test_sweep_opens_paid_claims_and_is_idempotent():
    db = _session()
    _seed_bad_provider(db)
    opened = aud.recovery_sweep(db, I, threshold=20)
    assert len(opened) == 3                              # the three paid clean claims
    items = list(db.scalars(select(models.AuditQueue)))
    assert all(a.status == "OPEN" and a.amount_at_stake == 500.0 for a in items)
    assert all("PR_BAD" in a.reason for a in items)
    assert aud.recovery_sweep(db, I, threshold=20) == []  # idempotent — no re-open


def test_review_recover_and_roi():
    db = _session()
    _seed_bad_provider(db)
    aid = aud.recovery_sweep(db, I, threshold=20)[0]
    aud.transition(db, aid, "review", I)
    a = aud.transition(db, aid, "recover", I, amount=500.0)
    assert a.status == "RECOVERED" and a.amount_recovered == 500.0
    assert a.recovery_outcome == "RECOVERED_FULL"
    r = aud.roi(db)
    assert r["amount_at_stake"] == 1500.0 and r["amount_recovered"] == 500.0
    assert r["recovery_rate"] == 33.3
    assert r["by_status"]["RECOVERED"] == 1 and r["by_status"]["OPEN"] == 2


def test_partial_recovery_outcome():
    db = _session()
    _seed_bad_provider(db)
    aid = aud.recovery_sweep(db, I, threshold=20)[0]
    aud.transition(db, aid, "review", I)
    a = aud.transition(db, aid, "recover", I, amount=200.0)
    assert a.recovery_outcome == "RECOVERED_PARTIAL"


def test_clear_false_positive():
    db = _session()
    _seed_bad_provider(db)
    aid = aud.recovery_sweep(db, I, threshold=20)[0]
    a = aud.transition(db, aid, "clear", I)
    assert a.status == "CLEARED" and a.recovery_outcome == "CLEARED"


def test_illegal_transition_and_wrong_actor():
    db = _session()
    _seed_bad_provider(db)
    aid = aud.recovery_sweep(db, I, threshold=20)[0]
    with pytest.raises(sm.IllegalTransition):
        aud.transition(db, aid, "recover", I)            # recover before review
    with pytest.raises(sm.WrongActor):
        aud.transition(db, aid, "review", H)             # handler may not review
