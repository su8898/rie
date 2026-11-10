"""Regression tests for the six blocker fixes from the 2026-11-09 review.

B1 default secrets refused outside dev / sessions re-checked against the DB · B2 dev users only
in dev · B3 payment amount, pay-once, three-way SoD, compare-and-set · B4 rails drop fund-side
facts, alg pinned, verdicts not public · B5 resubmission is 409, ADMIN rescore appends ·
B6 typed, bounded submissions."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid

import pytest
import test_api  # noqa: F401  (sets RIE_DATABASE_URL + imports the app first)
from fastapi.testclient import TestClient
from itsdangerous import TimestampSigner
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from server import config, jws, models, payments_service as pay, seed as seedmod, statemachine as sm
from server.config import check_secrets, insecure_secrets
from server.db import Base, SessionLocal
from server.main import app

client = TestClient(app)
SECRET = "rie-rails-dev-secret"
LINE = {"kind": "TARIFF", "code": "0190", "qty": 1, "amount": 500.0,
        "service_date": "2026-03-01", "provider_id": "PR_H", "dx": "S72"}


def _login(c, user):
    assert c.post("/api/auth/login", json={"username": user, "password": user}).status_code == 200


def _claim(cid, party, cas, **kw):
    return {"claim_id": cid, "claim_type": "SUPPLIER", "party_token": party,
            "accident_date": "2026-02-01", "lodged_on": "2026-03-01", "case_number_raw": cas,
            "today": "2026-07-05", "payee_verified": True,
            "documents": {"RAF2": True, "OAR": True, "INVOICES": True, "BANK": True},
            "lines": [dict(LINE)], **kw}


def _personal(cid, party, cas, **kw):
    return _claim(cid, party, cas, claim_type="PERSONAL",
                  documents={"RAF1": True, "OAR": True, "ID": True, "BANK": True}, **kw)


def _batch():
    return client.post("/api/payments/batches", json={}).json()["id"]


def _instr(bid, **body):
    return client.post(f"/api/payments/batches/{bid}/instructions", json=body)


# ── B1 ─────────────────────────────────────────────────────────────────────────────────────────
def test_check_secrets_refuses_defaults_outside_dev():
    with pytest.raises(RuntimeError) as e:
        check_secrets({"RIE_APP_ENV": "prod"})
    assert "RIE_SECRET_KEY" in str(e.value) and "RIE_PSEUDONYM_SECRET" in str(e.value)
    strong = {"RIE_APP_ENV": "prod", "RIE_SECRET_KEY": "k" * 40, "RIE_RAILS_SECRET": "r" * 40,
              "RIE_PSEUDONYM_SECRET": "p" * 40}
    check_secrets(strong)                                               # no raise
    assert insecure_secrets({**strong, "RIE_RAILS_SECRET": "short"}) == ["RIE_RAILS_SECRET"]
    check_secrets({"RIE_APP_ENV": "dev"})                               # dev defaults are allowed


def test_forged_cookie_for_unknown_user_is_rejected():
    payload = base64.b64encode(json.dumps({"user": {"username": "ghost", "role": "ADMIN"}}).encode())
    tok = TimestampSigner(config.SECRET_KEY).sign(payload).decode()
    c = TestClient(app)
    assert c.get("/api/admin/users", headers={"cookie": "session=" + tok}).status_code == 401


def test_role_and_deactivation_apply_to_live_sessions():
    admin = TestClient(app)
    _login(admin, "admin")
    assert admin.post("/api/admin/users", json={"username": "temp_legal", "role": "LEGAL",
                                                 "password": "temp_legal"}).status_code == 200
    u = TestClient(app)
    _login(u, "temp_legal")
    assert u.get("/api/auth/me").json()["role"] == "LEGAL"
    admin.post("/api/admin/users/temp_legal/role", json={"role": "HANDLER"})
    assert u.get("/api/auth/me").json()["role"] == "HANDLER"            # immediate, not at cookie expiry
    admin.post("/api/admin/users/temp_legal/active", json={"active": False})
    assert u.get("/api/claims").status_code == 401                      # deactivated -> out now


# ── B2 ─────────────────────────────────────────────────────────────────────────────────────────
def _fresh():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng)()


def test_dev_users_seeded_only_in_dev(monkeypatch):
    monkeypatch.setattr(seedmod, "SEED_DEV_USERS", False)
    monkeypatch.setattr(seedmod, "BOOTSTRAP_ADMIN_PASSWORD", "")
    db = _fresh()
    seedmod.seed_users(db)
    db.commit()
    assert db.scalar(select(func.count()).select_from(models.AppUser)) == 0   # prod: nothing seeded

    monkeypatch.setattr(seedmod, "BOOTSTRAP_ADMIN_PASSWORD", "correct horse battery staple")
    db = _fresh()
    seedmod.seed_users(db)
    db.commit()
    assert [(u.username, u.role) for u in db.scalars(select(models.AppUser))] == [("admin", "ADMIN")]

    monkeypatch.setattr(seedmod, "SEED_DEV_USERS", True)
    db = _fresh()
    seedmod.seed_users(db)
    db.commit()
    assert {u.username for u in db.scalars(select(models.AppUser))} >= {"admin", "treasury", "handler"}


def test_healthz_reports_env():
    assert client.get("/healthz").json()["env"] in ("dev", "test")


# ── B3 ─────────────────────────────────────────────────────────────────────────────────────────
def _settle(cid, party, cas) -> float:
    _login(client, "handler")
    assert client.post("/api/claims", json=_personal(cid, party, cas)).status_code == 200
    for a in ("validate", "open_merits"):
        client.post(f"/api/lifecycle/{cid}/{a}")
    client.post(f"/api/merits/{cid}/accept", json={"fault_pct": 0})
    client.post(f"/api/lifecycle/{cid}/accept_merits")
    offer = client.post(f"/api/offer/{cid}", json={}).json()
    client.post(f"/api/lifecycle/{cid}/make_offer")
    assert client.post(f"/api/lifecycle/{cid}/settle").json()["stage"] == "SETTLED"
    return offer["offer_total"]


def test_settlement_amount_must_match_offer_and_claim_pays_once():
    assert _settle("R_h3a", "P_h3a", "CAS 9400/02/2026") == 500.0
    b1 = _batch()
    r = _instr(b1, claim_id="R_h3a", source="SETTLEMENT", amount=99999999.99)
    assert r.status_code == 409 and "does not match" in r.json()["detail"]
    assert _instr(b1, claim_id="R_h3a", source="SETTLEMENT", amount=-500).status_code == 422
    assert _instr(b1, claim_id="R_h3a", source="SETTLEMENT", amount=0).status_code == 422
    r = _instr(b1, claim_id="R_h3a", source="SETTLEMENT", amount=500.0)
    assert r.status_code == 200 and r.json()["total"] == 500.0
    b2 = _batch()                                                       # second open batch, same claim
    r = _instr(b2, claim_id="R_h3a", source="SETTLEMENT")
    assert r.status_code == 409 and "paid once" in r.json()["detail"]
    assert client.post(f"/api/payments/batches/{b1}/cancel").json()["status"] == "CANCELLED"
    r = _instr(b2, claim_id="R_h3a", source="SETTLEMENT")               # cancelling frees the claim
    assert r.status_code == 200 and r.json()["total"] == 500.0


def test_supplier_amount_defaults_to_net_payable_and_must_match():
    _login(client, "handler")
    client.post("/api/claims", json=_claim("R_h3b", "P_h3b", "CAS 9401/02/2026"))
    bid = _batch()
    r = _instr(bid, claim_id="R_h3b", source="SUPPLIER", amount=1.0)
    assert r.status_code == 409 and "does not match" in r.json()["detail"]
    r = _instr(bid, claim_id="R_h3b", source="SUPPLIER")
    assert r.status_code == 200 and r.json()["total"] == 500.0
    assert _instr(_batch(), claim_id="R_h3b", source="SUPPLIER").status_code == 409   # pay once


def test_three_way_segregation_of_duties():
    _login(client, "handler")
    client.post("/api/claims", json=_claim("R_h3c", "P_h3c", "CAS 9402/02/2026"))
    bid = _batch()
    assert _instr(bid, claim_id="R_h3c", source="SUPPLIER").status_code == 200
    _login(client, "admin")
    assert client.post(f"/api/payments/batches/{bid}/approve").json()["status"] == "APPROVED"
    r = client.post(f"/api/payments/batches/{bid}/pay")
    assert r.status_code == 403 and "payer must differ" in r.json()["detail"]
    _login(client, "treasury")
    b = client.post(f"/api/payments/batches/{bid}/pay").json()
    assert b["status"] == "PAID" and b["paid_by"] == "treasury" and b["approved_by"] == "admin"


def test_concurrent_pay_is_refused_by_compare_and_set():
    _login(client, "handler")
    client.post("/api/claims", json=_claim("R_h3d", "P_h3d", "CAS 9403/02/2026"))
    bid = _batch()
    assert _instr(bid, claim_id="R_h3d", source="SUPPLIER").status_code == 200
    _login(client, "admin")
    client.post(f"/api/payments/batches/{bid}/approve")
    s1, s2 = SessionLocal(), SessionLocal()
    try:
        assert s1.get(models.PaymentBatch, bid).status == "APPROVED"
        assert s2.get(models.PaymentBatch, bid).status == "APPROVED"     # both see APPROVED
        pay.pay(s1, bid, {"username": "treasury", "role": "ADMIN"})
        with pytest.raises(sm.IllegalTransition):
            pay.pay(s2, bid, {"username": "treasury2", "role": "ADMIN"})
        s2.rollback()
        paid_events = s1.scalars(select(models.PaymentEvent).where(
            models.PaymentEvent.batch_id == bid, models.PaymentEvent.event == "PAID")).all()
        assert len(paid_events) == 1
    finally:
        s1.close()
        s2.close()


def test_queue_excludes_zero_rand_claims():
    _login(client, "handler")
    client.post("/api/claims", json=_claim("R_h3e", "P_h3e", "CAS 9404/02/2026",
                                            lines=[{**LINE, "amount": 0.0}]))
    assert "R_h3e" not in {q["claim_id"] for q in client.get("/api/payments/queue").json()}


# ── B4 ─────────────────────────────────────────────────────────────────────────────────────────
def _sign(body, header=None):
    header = header or {"alg": "HS256", "jti": str(uuid.uuid4()), "exp": int(time.time()) + 300}
    return jws.sign_detached(header, body, SECRET)


def _rails(body):
    return client.post("/rails/v1/claims", json=body, headers={
        "Idempotency-Key": str(uuid.uuid4()), "X-JWS-Signature": _sign(body)})


def test_rails_drops_fund_side_facts():
    body = _claim("R_h4a", "P_h4a", "CAS 9500/02/2026", merits_accepted=True, fault_pct=0,
                  attorney_in_standing=True, provider_registered=True)
    r = _rails(body)
    assert r.status_code == 200, r.text
    assert "PAYEE_UNVERIFIED" in r.json()["verdict"]["holds"]          # provider's payee_verified ignored
    _login(client, "handler")
    raw = client.get("/api/claims/R_h4a").json()["claim"]["raw"]
    for k in ("payee_verified", "merits_accepted", "fault_pct", "attorney_in_standing",
              "provider_registered", "today"):
        assert k not in raw
    r = _instr(_batch(), claim_id="R_h4a", source="SUPPLIER")
    assert r.status_code == 409 and "PAYEE_UNVERIFIED" in r.json()["detail"]


def test_rails_alg_none_is_rejected():
    body = _claim("R_h4b", "P_h4b", "CAS 9501/02/2026")
    h = jws._b64u(jws.canonical({"alg": "none", "jti": str(uuid.uuid4())}))
    b = jws._b64u(jws.canonical(body))
    mac = hmac.new(SECRET.encode(), f"{h}.{b}".encode(), hashlib.sha256).digest()
    r = client.post("/rails/v1/claims", json=body, headers={
        "Idempotency-Key": str(uuid.uuid4()), "X-JWS-Signature": f"{h}..{jws._b64u(mac)}"})
    assert r.status_code == 401


def test_rails_duplicate_claim_id_409_and_invalid_lines_422():
    body = _claim("R_h4c", "P_h4c", "CAS 9502/02/2026")
    assert _rails(body).status_code == 200
    assert _rails(dict(body)).status_code == 409                        # new key + jti, same claim_id
    bad = _claim("R_h4d", "P_h4d", "CAS 9503/02/2026", lines=[{**LINE, "qty": -1, "amount": -500}])
    assert _rails(bad).status_code == 422


def test_rails_readback_requires_signature_or_session():
    body = _claim("R_h4e", "P_h4e", "CAS 9504/02/2026")
    sid = _rails(body).json()["submissionId"]
    anon = TestClient(app)
    assert anon.get(f"/rails/v1/claims/{sid}").status_code == 401
    sig = _sign({"submissionId": sid})
    assert anon.get(f"/rails/v1/claims/{sid}", headers={"X-JWS-Signature": sig}).status_code == 200
    _login(client, "handler")
    assert client.get(f"/rails/v1/claims/{sid}").status_code == 200    # operator session also fine


# ── B5 ─────────────────────────────────────────────────────────────────────────────────────────
def test_resubmitting_claim_id_is_409_and_admin_rescore_appends():
    _login(client, "handler")
    assert client.post("/api/claims", json=_claim("R_h5", "P_h5", "CAS 9600/02/2026")).status_code == 200
    r = client.post("/api/claims", json=_claim("R_h5", "P_h5", "CAS 9600/02/2026",
                                                lines=[{**LINE, "qty": 3, "amount": 2700.0}]))
    assert r.status_code == 409
    d = client.get("/api/claims/R_h5").json()
    assert d["determination"]["medical_payable"] == 500.0 and d["claim"]["raw"]["lines"][0]["amount"] == 500.0
    assert client.post("/api/claims/R_h5/rescore").status_code == 403  # ADMIN only
    _login(client, "admin")
    r = client.post("/api/claims/R_h5/rescore", json={"note": "post-review re-determination"})
    assert r.status_code == 200 and r.json()["medical_payable"] == 500.0
    assert len([x for x in client.get("/api/claims?q=R_h5").json() if x["claim_id"] == "R_h5"]) == 2
    assert any(a["action"] == "RESCORE_CLAIM" and a["target"] == "R_h5"
               for a in client.get("/api/admin/audit").json())
    assert client.post("/api/claims/R_nope/rescore").status_code == 404


# ── B6 ─────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("patch, marker", [
    ({"lines": [{**LINE, "qty": -1, "amount": -500}]}, "qty"),
    ({"lines": [{**LINE, "qty": 0}]}, "qty"),
    ({"lines": [{**LINE, "kind": "BANANA"}]}, "kind"),
    ({"lines": [{**LINE, "amount": 1e12}]}, "amount"),
    ({"documents": {"RAF2": "missing", "OAR": "no", "INVOICES": "0", "BANK": "pending"}}, "documents"),
    ({"fault_pct": 150}, "fault_pct"),
    ({"merits_accepted": False, "merits_ground": "OTHER"}, "merits_ground"),
    ({"party_token": "8001015009087"}, "party_token"),
    ({"claim_type": "MEDICAL"}, "claim_type"),
    ({"lodged_on": "2026-01-01"}, "lodged_on"),
])
def test_submission_validation_422(patch, marker):
    _login(client, "handler")
    body = {**_claim("R_h6_" + marker, "P_h6", "CAS 9700/02/2026"), **patch}
    r = client.post("/api/claims", json=body)
    assert r.status_code == 422, r.text
    assert marker in json.dumps(r.json())


def test_valid_submission_still_scores():
    _login(client, "handler")
    r = client.post("/api/claims", json=_claim("R_h6_ok", "P_h6ok", "CAS 9701/02/2026"))
    assert r.status_code == 200 and r.json()["disposition"] == "CLEAN"


def test_merits_api_bounds():
    _login(client, "handler")
    client.post("/api/claims", json=_personal("R_h6m", "P_h6m", "CAS 9702/02/2026"))
    for a in ("validate", "open_merits"):
        client.post(f"/api/lifecycle/R_h6m/{a}")
    assert client.post("/api/merits/R_h6m/accept", json={"fault_pct": 150}).status_code == 422
    r = client.post("/api/merits/R_h6m/reject", json={"ground": "OTHER"})
    assert r.status_code == 409 and "must be one of" in r.json()["detail"]
    assert client.post("/api/merits/R_h6m/reject", json={"ground": "SOLE_NEGLIGENCE"}).json()["status"] == "REJECTED"
