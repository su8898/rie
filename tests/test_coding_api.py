"""Coding intelligence (SPECIFICATION §6) — aggregation/overage, condition bands, negotiation targets."""
from __future__ import annotations

from datetime import date

import test_api  # noqa: F401  (sets RIE_DATABASE_URL + imports the app + seeds)
from fastapi.testclient import TestClient
from server import coding_service as svc, models
from server.db import SessionLocal
from server.main import app

client = TestClient(app)


def _login(user="handler"):
    assert client.post("/api/auth/login", json={"username": user, "password": user}).status_code == 200


def _seed_lines(code, specs):
    # specs: (billed, reference, payable, legal_status, src)
    with SessionLocal() as db:
        for i, (b, ref, pay, ls, src) in enumerate(specs):
            db.add(models.BillingLineRecord(claim_id=f"C_{code}_{i}", provider_id=f"PRV{i % 3}",
                   kind="TARIFF", code=code, billed=b, reference=ref, payable=pay, src=src,
                   legal_status=ls, needs_review=False, reasons=[]))
        db.commit()


def _seed_condition(dx, n, base=1000.0, step=100.0, discipline="GP"):
    with SessionLocal() as db:
        for i in range(n):
            cid = f"ZC_{dx}_{i}"
            db.add(models.ClaimRecord(claim_id=cid, claim_type="SUPPLIER", party_token="P",
                   accident_date=date(2026, 2, 1), lodged_on=date(2026, 3, 1),
                   raw={"lines": [{"kind": "TARIFF", "code": "0190", "amount": 500,
                                   "dx": dx, "discipline": discipline}]}))
            db.add(models.Determination(claim_id=cid, accident_id="A", accident_action="CREATED",
                   band="GREEN", score=0, disposition="CLEAN", validated=True, convergence=0.0,
                   medical_payable=base + i * step, net_payable=0.0, eligible_to_pay=True,
                   reasons=[], shadow_signals=[], holds=[], engine_version="t",
                   ruleset_effective="", reference_edition=""))
        db.commit()


def test_code_aggregation_buckets_overage():
    _seed_lines("ZZAGG", [
        (1000, 500, 500, "ACCEPTED", "RPL"),            # repriced -> captured 500
        (800, 300, 800, "INTERDICTED", "RAF 2022"),     # over-signal 500 (paid full, not captured)
        (400, None, 400, None, "—"),                    # uncovered 400
    ])
    with SessionLocal() as db:
        a = {(r["kind"], r["code"]): r for r in svc.code_aggregation(db)}[("TARIFF", "ZZAGG")]
    assert a["n_lines"] == 3 and a["billed"] == 2200.0 and a["n_providers"] == 3
    assert a["repricing_captured"] == 500.0 and a["over_reference_signal"] == 500.0
    assert a["uncovered_billed"] == 400.0 and a["uncovered_lines"] == 1


def test_negotiation_targets_rank_and_exclude_negotiated():
    _seed_lines("ZZNEG", [(900, 300, 900, "INTERDICTED", "RAF 2022")])   # signal 600
    with SessionLocal() as db:
        db.add(models.RefNegotiated(kind="TARIFF", code="ZZNEG2", rate=100.0))
        db.commit()
    _seed_lines("ZZNEG2", [(900, 300, 900, "INTERDICTED", "RAF 2022")])  # negotiated -> excluded
    with SessionLocal() as db:
        targets = {r["code"]: r for r in svc.negotiation_targets(db)}
    assert targets["ZZNEG"]["potential_saving"] == 600.0
    assert "ZZNEG2" not in targets


def test_condition_bands_min_robust_and_intensity_split():
    _seed_condition("Z99", 25)                          # robust (>= MIN_ROBUST 20)
    _seed_condition("Z88", 5)                           # small-n
    with SessionLocal() as db:
        bands = {r["injury_class"]: r for r in svc.condition_bands(db)}
    z99 = bands["Z99"]
    assert z99["robust"] is True and z99["n"] >= 25
    b = z99["bands"]
    assert b["p25"] < b["p50"] < b["p75"] <= b["p90"] <= b["max"]
    assert z99["by_intensity"]["CONSERVATIVE"]["n"] >= 25
    assert bands["Z88"]["robust"] is False and bands["Z88"]["bands"] is None


def test_estimate_classifies_amount():
    _seed_condition("Y99", 25, base=1000.0, step=100.0)   # totals 1000..3400; p25~1600 p75~2800 p90~3160
    with SessionLocal() as db:
        assert svc.estimate(db, "Y99", 1200)["classification"] == "BELOW_TYPICAL"
        assert svc.estimate(db, "Y99", 2200)["classification"] == "TYPICAL"
        assert svc.estimate(db, "Y99", 3000)["classification"] == "HIGH"
        assert svc.estimate(db, "Y99", 3400)["classification"] == "OUTLIER"
        assert svc.estimate(db, "NOPE", 100)["robust"] is False


def test_coding_api_and_auth():
    _seed_lines("ZZAPI", [(700, 200, 700, "INTERDICTED", "RAF 2022")])
    _login()
    codes = {r["code"] for r in client.get("/api/coding/codes", params={"kind": "TARIFF"}).json()}
    assert "ZZAPI" in codes
    assert isinstance(client.get("/api/coding/negotiation-targets").json(), list)
    assert isinstance(client.get("/api/coding/conditions").json(), list)
    client.post("/api/auth/logout")
    assert client.get("/api/coding/codes").status_code == 401
