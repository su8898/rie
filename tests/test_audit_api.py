"""Audit endpoints — HTTP wiring smoke over the shared app (counts are corpus-dependent)."""
from __future__ import annotations

import test_api  # noqa: F401  (sets RIE_DATABASE_URL + imports the app first)
from fastapi.testclient import TestClient
from server.main import app

client = TestClient(app)


def _login(user="investigator"):
    assert client.post("/api/auth/login", json={"username": user, "password": user}).status_code == 200


def test_audit_endpoints_wired():
    _login("investigator")
    assert client.get("/api/audit").status_code == 200
    sweep = client.post("/api/audit/sweep", params={"threshold": 10}).json()
    assert "n" in sweep and "opened" in sweep
    roi = client.get("/api/audit/roi").json()
    assert {"n_items", "amount_at_stake", "amount_recovered", "recovery_rate"} <= set(roi)


def test_sweep_requires_investigator():
    _login("handler")
    assert client.post("/api/audit/sweep").status_code == 403


def test_transition_flow_if_any_open():
    _login("investigator")
    client.post("/api/audit/sweep", params={"threshold": 5})
    items = client.get("/api/audit", params={"status": "OPEN"}).json()
    if items:                                            # if the sweep opened anything, drive one
        aid = items[0]["id"]
        assert client.post(f"/api/audit/{aid}/review").json()["status"] == "UNDER_REVIEW"
        done = client.post(f"/api/audit/{aid}/recover", json={"amount": 100.0}).json()
        assert done["status"] == "RECOVERED" and done["amount_recovered"] == 100.0
