"""Leakage decomposition — isolated in-memory DB, deterministic buckets."""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from server.db import Base
from server.leakage_service import claim_leakage, portfolio_leakage
from server.pipeline_service import assess_and_store
from server.seed import seed


def _session():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    db = sessionmaker(bind=eng)()
    seed(db)
    return db


def _supplier(cid, party, cas, lines):
    return {"claim_id": cid, "claim_type": "SUPPLIER", "party_token": party,
            "accident_date": "2026-02-01", "lodged_on": "2026-03-01", "case_number_raw": cas,
            "today": "2026-07-05", "payee_verified": True,
            "documents": {"RAF2": True, "OAR": True, "INVOICES": True, "BANK": True},
            "lines": lines}


def _line(code="0190", amount=500.0):
    return {"kind": "TARIFF", "code": code, "qty": 1, "amount": amount,
            "service_date": "2026-03-01", "provider_id": "PR1", "dx": "S72"}


def test_repricing_saving():
    db = _session()
    assess_and_store(db, _supplier("R_a", "P_a", "CAS 1/02/2026", [_line(amount=800.0)]))
    d = claim_leakage(db, "R_a")
    assert d["billed_total"] == 800.0
    assert d["within_reference"] == 500.0      # repriced to RPL
    assert d["repricing_saving"] == 300.0
    assert d["over_reference_signal"] == 0.0
    assert d["uncovered"] == 0.0


def test_interdicted_over_signal():
    db = _session()
    assess_and_store(db, _supplier("R_b", "P_b", "CAS 2/02/2026", [_line(code="0200", amount=400.0)]))
    d = claim_leakage(db, "R_b")
    assert d["within_reference"] == 400.0       # interdicted → paid as billed
    assert d["over_reference_signal"] == 100.0  # signal only (400 − 300)
    assert d["repricing_saving"] == 0.0


def test_dedupe_and_uncovered():
    db = _session()
    p = _supplier("R_c", "P_c", "CAS 3/02/2026",
                  [_line(amount=500.0), _line(amount=500.0), _line(code="7777", amount=250.0)])
    assess_and_store(db, p)
    d = claim_leakage(db, "R_c")
    assert d["within_reference"] == 500.0        # first line paid
    assert d["dedupe_exposure"] == 500.0         # duplicate held
    assert d["uncovered"] == 250.0               # no reference


def test_portfolio_aggregates():
    db = _session()
    assess_and_store(db, _supplier("R_a", "P_a", "CAS 1/02/2026", [_line(amount=800.0)]))
    assess_and_store(db, _supplier("R_b", "P_b", "CAS 2/02/2026", [_line(code="0200", amount=400.0)]))
    d = portfolio_leakage(db)
    assert d["repricing_saving"] == 300.0
    assert d["over_reference_signal"] == 100.0
    assert d["lines"] == 2
