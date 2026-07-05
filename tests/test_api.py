"""End-to-end API tests — auth, RBAC, submit→score→persist, accident graph, dashboard.

Uses an isolated temp SQLite DB and FastAPI's TestClient (real HTTP stack, real engine, real
persistence). The DATABASE_URL is set before importing the app so init_db() targets the temp DB.
"""
from __future__ import annotations

import os
import tempfile

_fd, _path = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.environ["RIE_DATABASE_URL"] = "sqlite:///" + _path

from fastapi.testclient import TestClient  # noqa: E402
from server.main import app  # noqa: E402

client = TestClient(app)

CLAIM = {
    "claim_id": "R_100", "claim_type": "SUPPLIER", "party_token": "P_100",
    "accident_date": "2026-02-01", "lodged_on": "2026-03-01",
    "case_number_raw": "CAS 100/02/2026", "today": "2026-07-05",
    "documents": {"RAF2": True, "OAR": True, "INVOICES": True, "BANK": True},
    "payee_verified": True,
    "lines": [{"kind": "TARIFF", "code": "0190", "qty": 1, "amount": 500.0,
               "service_date": "2026-03-01", "provider_id": "PR1", "dx": "S72"}],
}


def _login(user="handler"):
    r = client.post("/api/auth/login", json={"username": user, "password": user})
    assert r.status_code == 200, r.text
    return r


def test_healthz():
    r = client.get("/healthz")
    assert r.status_code == 200 and r.json()["db"] == "up"


def test_auth_me_requires_login():
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401
    _login("handler")
    me = client.get("/api/auth/me").json()
    assert me["role"] == "HANDLER"


def test_login_bad_credentials():
    assert client.post("/api/auth/login",
                       json={"username": "handler", "password": "nope"}).status_code == 401


def test_submit_rbac():
    client.post("/api/auth/logout")
    assert client.post("/api/claims", json=CLAIM).status_code == 401
    _login("investigator")                       # not a submit lane
    assert client.post("/api/claims", json=CLAIM).status_code == 403


def test_submit_clean_and_read_back():
    _login("handler")
    rec = client.post("/api/claims", json=CLAIM).json()
    assert rec["band"] == "GREEN"
    assert rec["disposition"] == "CLEAN"
    assert rec["eligible_to_pay"] is True
    assert rec["medical_payable"] == 500.0
    assert rec["accident_action"] == "CREATED"
    body = client.get("/api/claims/R_100").json()
    assert body["determination"]["band"] == "GREEN"
    assert body["claim"]["claim_type"] == "SUPPLIER"


def test_submit_over_rpl_reprices():
    _login("handler")
    c = {**CLAIM, "claim_id": "R_over", "party_token": "P_over",
         "case_number_raw": "CAS 200/02/2026",
         "lines": [{**CLAIM["lines"][0], "amount": 800.0}]}
    j = client.post("/api/claims", json=c).json()
    assert j["disposition"] == "ADJUSTED"
    assert j["medical_payable"] == 500.0            # repriced from 800
    assert "BILLED_OVER_REFERENCE" in j["reasons"]


def test_personal_merits_pending_held():
    _login("handler")
    c = {**CLAIM, "claim_id": "R_p", "claim_type": "PERSONAL", "party_token": "P_p",
         "case_number_raw": "CAS 300/02/2026",
         "documents": {"RAF1": True, "OAR": True, "ID": True, "BANK": True}}
    j = client.post("/api/claims", json=c).json()
    assert j["disposition"] == "MERITS"
    assert j["eligible_to_pay"] is False
    assert "held_for_merits" in j["holds"]


def test_accident_graph_join():
    _login("handler")
    a = {**CLAIM, "claim_id": "R_a", "party_token": "P_a", "case_number_raw": "CAS 555/03/2026",
         "accident_date": "2026-03-10", "lodged_on": "2026-03-20",
         "lines": [{**CLAIM["lines"][0], "service_date": "2026-03-11"}]}
    b = {**a, "claim_id": "R_b", "party_token": "P_b"}
    r1 = client.post("/api/claims", json=a).json()
    r2 = client.post("/api/claims", json=b).json()
    assert r1["accident_action"] == "CREATED"
    assert r2["accident_action"] == "JOINED"
    assert r1["accident_id"] == r2["accident_id"]
    accs = client.get("/api/accidents").json()
    match = next(x for x in accs if x["accident_id"] == r1["accident_id"])
    assert match["n_claims"] == 2


def test_submit_missing_field_422():
    _login("handler")
    assert client.post("/api/claims", json={"claim_id": "x"}).status_code == 422


def test_reasons_catalogue():
    _login("handler")
    cat = client.get("/api/reasons").json()
    codes = {x["code"] for x in cat}
    assert "PRESCRIBED_LODGEMENT" in codes and "RING_PARTIES" in codes
    ring = next(x for x in cat if x["code"] == "RING_PARTIES")
    assert ring["mode"] == "SHADOW"                 # unvalidated launches shadow


def test_dashboard():
    _login("handler")
    d = client.get("/api/dashboard").json()
    assert d["determinations"] >= 1
    assert set(d["by_band"]) == {"GREEN", "AMBER", "RED"}
    assert d["net_payable_total"] >= 0.0
