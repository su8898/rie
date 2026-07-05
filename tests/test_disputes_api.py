"""Disputes module — the s91-objection pattern generalised (SPECIFICATION §6).

Three paths: INTERNAL reconsideration, HPCSA tribunal (serious injury), litigation hand-off.
State-machine discipline: illegal -> 409, wrong actor -> 403, invalid enum -> 409, actor-stamped log.
"""
from __future__ import annotations

import test_api  # noqa: F401  (sets RIE_DATABASE_URL + imports the app first)
from fastapi.testclient import TestClient
from server.main import app

client = TestClient(app)


def _login(user="handler"):
    assert client.post("/api/auth/login", json={"username": user, "password": user}).status_code == 200


def _lodge(subject="MERITS", raised_by="ATTORNEY", claim_id="R_disp", grounds="g") -> dict:
    return client.post("/api/disputes", json={"claim_id": claim_id, "subject": subject,
                                              "raised_by": raised_by, "grounds": grounds}).json()


def test_internal_reconsideration_upheld():
    _login("handler")
    d = _lodge("QUANTUM", "CLAIMANT")
    did = d["id"]
    assert d["status"] == "LODGED" and d["days_to_deadline"] is not None and d["overdue"] is False
    assert client.post(f"/api/disputes/{did}/reconsider").json()["channel"] == "INTERNAL"
    r = client.post(f"/api/disputes/{did}/uphold", json={"outcome": "offer revised upward"}).json()
    assert r["status"] == "UPHELD" and r["outcome"] == "offer revised upward" and r["closed_at"]


def test_serious_injury_refers_to_hpcsa_tribunal():
    _login("legal")
    did = _lodge("SERIOUS_INJURY", "CLAIMANT")["id"]
    r = client.post(f"/api/disputes/{did}/refer").json()          # LEGAL refers; SI -> HPCSA tribunal
    assert r["status"] == "REFERRED" and r["channel"] == "HPCSA_TRIBUNAL"
    r = client.post(f"/api/disputes/{did}/resolve", json={"outcome": "TRIBUNAL_UPHELD"}).json()
    assert r["status"] == "RESOLVED" and r["outcome"] == "TRIBUNAL_UPHELD"


def test_rejected_reconsideration_hands_off_to_litigation():
    _login("handler")
    did = _lodge("MERITS", "ATTORNEY")["id"]
    client.post(f"/api/disputes/{did}/reconsider")
    client.post(f"/api/disputes/{did}/reject", json={"outcome": "apportionment stands"})
    client.post("/api/auth/logout")
    _login("legal")
    r = client.post(f"/api/disputes/{did}/refer").json()          # default channel LITIGATION + hand-off
    assert r["status"] == "REFERRED" and r["channel"] == "LITIGATION"
    assert r["linked_ref"].startswith("litigation:")
    # the litigation record was actually opened
    from server import models
    from server.db import SessionLocal
    with SessionLocal() as db:
        lit = db.get(models.Litigation, int(r["linked_ref"].split(":")[1]))
    assert lit is not None and lit.status == "SUMMONS_SERVED"


def test_illegal_transition_is_409():
    _login("legal")
    did = _lodge()["id"]
    assert client.post(f"/api/disputes/{did}/resolve").status_code == 409   # can't resolve from LODGED


def test_wrong_actor_refer_is_403():
    _login("handler")
    did = _lodge()["id"]
    assert client.post(f"/api/disputes/{did}/refer").status_code == 403     # refer is LEGAL-only


def test_invalid_subject_raiser_channel_are_409():
    _login("handler")
    assert client.post("/api/disputes",
                       json={"claim_id": "R", "subject": "NOPE", "raised_by": "CLAIMANT"}).status_code == 409
    assert client.post("/api/disputes",
                       json={"claim_id": "R", "subject": "MERITS", "raised_by": "ALIEN"}).status_code == 409
    did = _lodge()["id"]
    client.post("/api/auth/logout")
    _login("legal")
    assert client.post(f"/api/disputes/{did}/refer", json={"channel": "BOGUS"}).status_code == 409


def test_withdraw_from_lodged():
    _login("handler")
    did = _lodge()["id"]
    assert client.post(f"/api/disputes/{did}/withdraw").json()["status"] == "WITHDRAWN"


def test_analytics_and_actor_stamped_history():
    _login("legal")
    did = _lodge("TARIFF", "PROVIDER")["id"]
    client.post(f"/api/disputes/{did}/refer")
    a = client.get("/api/disputes/analytics").json()
    assert a["by_subject"].get("TARIFF", 0) >= 1 and a["by_channel"].get("LITIGATION", 0) >= 1
    from sqlalchemy import select
    from server import models
    from server.db import SessionLocal
    with SessionLocal() as db:
        rows = list(db.scalars(select(models.TransitionLog).where(
            models.TransitionLog.entity_type == "dispute",
            models.TransitionLog.entity_id == str(did))))
    assert any(r.action == "refer" and r.actor == "legal" for r in rows)


def test_disputes_require_auth():
    client.post("/api/auth/logout")
    assert client.get("/api/disputes").status_code == 401
