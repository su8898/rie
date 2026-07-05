"""Notifications (§12.8) — POPIA-minimal templates, opt-in channel, lifecycle-driven outbox."""
from __future__ import annotations

import test_api  # noqa: F401  (sets RIE_DATABASE_URL + imports the app + seeds)
from fastapi.testclient import TestClient
from server import notifications_service as svc
from server.db import SessionLocal
from server.main import app

client = TestClient(app)


def _login(user="handler"):
    assert client.post("/api/auth/login", json={"username": user, "password": user}).status_code == 200


def _claim(cid, party):
    return {"claim_id": cid, "claim_type": "SUPPLIER", "party_token": party,
            "accident_date": "2026-02-01", "lodged_on": "2026-03-01",
            "case_number_raw": f"CAS {cid}/02/2026", "today": "2026-07-05",
            "documents": {"RAF2": True, "OAR": True, "INVOICES": True, "BANK": True},
            "payee_verified": True,
            "lines": [{"kind": "TARIFF", "code": "0190", "qty": 1, "amount": 500.0,
                       "service_date": "2026-03-01", "provider_id": "PR1", "dx": "S72"}]}


def test_templates_are_popia_minimal():
    banned = {"medical", "diagnosis", "wpi", "rand", "injury", "icd", "earnings", "damages", "amount"}
    for tmpl in svc.TEMPLATES.values():
        assert not any(c.isdigit() for c in tmpl)           # no baked amounts / dates
        assert not any(w in tmpl.lower() for w in banned)   # never medical or quantum detail
        assert "{claim}" in tmpl                             # references the claim by pseudonym


def test_emit_ignores_events_without_a_template():
    with SessionLocal() as db:
        assert svc.emit(db, "MERITS", "R_anything") is None  # internal stage -> silent


def test_optin_pending_vs_no_optin_suppressed():
    _login("handler")
    client.post("/api/claims", json=_claim("R_nin", "P_nin"))
    client.post("/api/claims", json=_claim("R_nout", "P_nout"))
    client.post("/api/notifications/prefs/P_nin", json={"channel": "SMS", "opted_in": True})
    client.post("/api/lifecycle/R_nin/validate")
    client.post("/api/lifecycle/R_nout/validate")
    nin = client.get("/api/notifications", params={"claim_id": "R_nin"}).json()[0]
    nout = client.get("/api/notifications", params={"claim_id": "R_nout"}).json()[0]
    assert nin["event"] == "VALIDATED" and nin["status"] == "PENDING" and nin["channel"] == "SMS"
    assert nout["event"] == "VALIDATED" and nout["status"] == "SUPPRESSED"   # no opt-in
    assert "R_nin" in nin["body"] and "medical" not in nin["body"].lower()


def test_multiple_lifecycle_events_and_delivery():
    _login("handler")
    client.post("/api/claims", json=_claim("R_nfull", "P_nfull"))
    client.post("/api/notifications/prefs/P_nfull", json={"channel": "EMAIL", "opted_in": True})
    client.post("/api/lifecycle/R_nfull/validate")           # VALIDATED (emitted)
    client.post("/api/lifecycle/R_nfull/open_merits")        # MERITS (silent — internal)
    client.post("/api/lifecycle/R_nfull/repudiate")          # REPUDIATED (emitted)
    events = [n["event"] for n in client.get("/api/notifications", params={"claim_id": "R_nfull"}).json()]
    assert "VALIDATED" in events and "REPUDIATED" in events and "MERITS" not in events
    pending = client.get("/api/notifications", params={"claim_id": "R_nfull", "status": "PENDING"}).json()
    sent = client.post(f"/api/notifications/{pending[0]['id']}/sent").json()
    assert sent["status"] == "SENT" and sent["sent_at"]


def test_prefs_default_and_invalid_channel():
    _login()
    assert client.get("/api/notifications/prefs/P_unknown").json() == {
        "party_token": "P_unknown", "channel": "NONE", "opted_in": False}
    assert client.post("/api/notifications/prefs/P_x",
                       json={"channel": "CARRIER_PIGEON", "opted_in": True}).status_code == 400


def test_mark_sent_unknown_is_404_and_auth_required():
    _login()
    assert client.post("/api/notifications/99999999/sent").status_code == 404
    client.post("/api/auth/logout")
    assert client.get("/api/notifications").status_code == 401
