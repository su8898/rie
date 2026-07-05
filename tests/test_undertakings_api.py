"""Undertaking + invoice state machines end-to-end over HTTP — issue → activate → invoice →
adjudicate → approve → pay, plus suspend/resume/terminate and the enforcement failure modes
(scope gate 409, illegal transition 409, wrong actor 403)."""
from __future__ import annotations

import test_api  # noqa: F401  (sets RIE_DATABASE_URL + imports the app first)
from fastapi.testclient import TestClient
from server.main import app

client = TestClient(app)

PERSONAL = {
    "claim_type": "PERSONAL", "accident_date": "2026-02-01", "lodged_on": "2026-03-01",
    "today": "2026-07-05", "payee_verified": True,
    "documents": {"RAF1": True, "OAR": True, "ID": True, "BANK": True},
    "lines": [{"kind": "TARIFF", "code": "0190", "qty": 1, "amount": 500.0,
               "service_date": "2026-03-01", "provider_id": "PR1", "dx": "S72"}],
}


def _login(user="handler"):
    assert client.post("/api/auth/login",
                       json={"username": user, "password": user}).status_code == 200


def _submit(cid, party, cas):
    _login("handler")
    assert client.post("/api/claims", json={**PERSONAL, "claim_id": cid, "party_token": party,
                                            "case_number_raw": cas}).status_code == 200


def _issue(claim_id, scope_dx, origin="SETTLEMENT"):
    _login("medical")
    r = client.post("/api/undertakings",
                    json={"claim_id": claim_id, "origin": origin, "scope_dx": scope_dx})
    assert r.status_code == 200, r.text
    return r.json()


def test_full_undertaking_and_invoice_flow():
    _submit("R_u1", "P_u1", "CAS 8201/02/2026")
    u = _issue("R_u1", ["S72"])
    assert u["status"] == "ISSUED" and u["origin"] == "SETTLEMENT" and u["scope_dx"] == ["S72"]
    uid = u["id"]

    # invoice submission is gated: the undertaking must be ACTIVE first.
    _login("medical")
    assert client.post(f"/api/undertakings/{uid}/invoices",
                       json={"billed": 500.0, "dx": "S72"}).status_code == 409

    # activate (HANDLER or MEDICAL_OFFICER) → ACTIVE
    r = client.post(f"/api/undertakings/{uid}/state/activate")
    assert r.status_code == 200 and r.json()["status"] == "ACTIVE"

    # now the invoice lands as RECEIVED, in-scope so no reasons.
    inv = client.post(f"/api/undertakings/{uid}/invoices",
                      json={"billed": 500.0, "dx": "S72"}).json()
    assert inv["status"] == "RECEIVED" and inv["reasons"] == [] and inv["payable"] == 0.0
    inv_id = inv["id"]

    # adjudicate (MEDICAL_OFFICER) sets payable, then approve → PAYABLE.
    adj = client.post(f"/api/undertakings/invoices/{inv_id}/adjudicate",
                      json={"approved": 450.0}).json()
    assert adj["status"] == "ADJUDICATED" and adj["payable"] == 450.0
    assert client.post(
        f"/api/undertakings/invoices/{inv_id}/state/approve").json()["status"] == "PAYABLE"

    # pay requires ADMIN.
    assert client.post(f"/api/undertakings/invoices/{inv_id}/state/pay").status_code == 403
    _login("admin")
    assert client.post(
        f"/api/undertakings/invoices/{inv_id}/state/pay").json()["status"] == "PAID"

    # read-back: undertaking carries its invoices + history.
    _login("handler")
    body = client.get(f"/api/undertakings/{uid}").json()
    assert body["status"] == "ACTIVE"
    assert len(body["invoices"]) == 1 and body["invoices"][0]["status"] == "PAID"
    assert [x["to"] for x in body["history"]] == ["ACTIVE"]


def test_out_of_scope_invoice_flagged_and_rejected():
    _submit("R_u2", "P_u2", "CAS 8202/02/2026")
    uid = _issue("R_u2", ["S72"])["id"]
    _login("medical")
    assert client.post(f"/api/undertakings/{uid}/state/activate").status_code == 200
    # dx S80 shares no 3-char prefix with scope S72 → UNDERTAKING_SCOPE flag.
    inv = client.post(f"/api/undertakings/{uid}/invoices",
                      json={"billed": 300.0, "dx": "S80"}).json()
    assert inv["reasons"] == ["UNDERTAKING_SCOPE"]
    inv_id = inv["id"]
    assert client.post(f"/api/undertakings/invoices/{inv_id}/adjudicate",
                       json={"approved": 0.0}).json()["status"] == "ADJUDICATED"
    assert client.post(
        f"/api/undertakings/invoices/{inv_id}/state/reject").json()["status"] == "REJECTED"


def test_suspend_resume_terminate():
    _submit("R_u3", "P_u3", "CAS 8203/02/2026")
    uid = _issue("R_u3", ["S72"])["id"]
    _login("medical")
    assert client.post(f"/api/undertakings/{uid}/state/activate").json()["status"] == "ACTIVE"
    # INVESTIGATOR may suspend / resume.
    _login("investigator")
    assert client.post(f"/api/undertakings/{uid}/state/suspend").json()["status"] == "SUSPENDED"
    assert client.post(f"/api/undertakings/{uid}/state/resume").json()["status"] == "ACTIVE"
    # ADMIN terminates from ACTIVE.
    _login("admin")
    assert client.post(f"/api/undertakings/{uid}/state/terminate").json()["status"] == "TERMINATED"


def test_lapse_from_active():
    _submit("R_u4", "P_u4", "CAS 8204/02/2026")
    uid = _issue("R_u4", ["S72"])["id"]
    _login("medical")
    assert client.post(f"/api/undertakings/{uid}/state/activate").json()["status"] == "ACTIVE"
    _login("admin")
    assert client.post(f"/api/undertakings/{uid}/state/lapse").json()["status"] == "LAPSED"


def test_bad_origin_rejected():
    _submit("R_u5", "P_u5", "CAS 8205/02/2026")
    _login("medical")
    r = client.post("/api/undertakings",
                    json={"claim_id": "R_u5", "origin": "WHATEVER", "scope_dx": ["S72"]})
    assert r.status_code == 409


def test_illegal_transition_409():
    _submit("R_u6", "P_u6", "CAS 8206/02/2026")
    uid = _issue("R_u6", ["S72"])["id"]
    _login("medical")
    # no 'suspend' from ISSUED (must activate first).
    assert client.post(f"/api/undertakings/{uid}/state/suspend").status_code == 409


def test_wrong_actor_403_on_suspend():
    _submit("R_u7", "P_u7", "CAS 8207/02/2026")
    uid = _issue("R_u7", ["S72"])["id"]
    _login("medical")
    assert client.post(f"/api/undertakings/{uid}/state/activate").json()["status"] == "ACTIVE"
    # HANDLER is not an INVESTIGATOR/MEDICAL_OFFICER → cannot suspend.
    _login("handler")
    assert client.post(f"/api/undertakings/{uid}/state/suspend").status_code == 403


def test_wrong_actor_403_on_adjudicate():
    _submit("R_u8", "P_u8", "CAS 8208/02/2026")
    uid = _issue("R_u8", ["S72"])["id"]
    _login("medical")
    assert client.post(f"/api/undertakings/{uid}/state/activate").json()["status"] == "ACTIVE"
    inv_id = client.post(f"/api/undertakings/{uid}/invoices",
                         json={"billed": 100.0, "dx": "S72"}).json()["id"]
    # INVESTIGATOR may not adjudicate an invoice (MEDICAL_OFFICER only).
    _login("investigator")
    assert client.post(f"/api/undertakings/invoices/{inv_id}/adjudicate",
                       json={"approved": 100.0}).status_code == 403


def test_missing_undertaking_404():
    _login("handler")
    assert client.get("/api/undertakings/999999").status_code == 404
