"""Cases module — the CIE case machine (domain-logic §8e): lanes, SLA, outcome capture, labels.

State-machine discipline: illegal transition -> 409, wrong actor -> 403, lane-ownership gate ->
409, actor-stamped history row written.
"""
from __future__ import annotations

import test_api  # noqa: F401  (sets RIE_DATABASE_URL + imports the app first)
from fastapi.testclient import TestClient
from server.main import app

client = TestClient(app)


def _login(user="handler"):
    assert client.post("/api/auth/login", json={"username": user, "password": user}).status_code == 200


def _open(lane="REVIEW", reason="r", priority=3, rand=0.0, claim_id=None) -> dict:
    return client.post("/api/cases", json={"lane": lane, "reason": reason, "priority": priority,
                                           "rand_at_stake": rand, "claim_id": claim_id}).json()


def test_review_case_full_lifecycle_with_outcome_capture():
    _login("handler")
    c = _open("REVIEW", "supplier over-reference", priority=2, rand=12500.0)
    cid = c["id"]
    assert c["status"] == "OPEN" and c["lane"] == "REVIEW" and c["owner_role"] == "HANDLER"
    assert c["sla_days"] == 3 and c["overdue"] is False and c["rand_at_stake"] == 12500.0
    assert "assign" in c["actions"]
    r = client.post(f"/api/cases/{cid}/assign").json()
    assert r["status"] == "IN_REVIEW" and r["assigned_to"] == "handler"
    r = client.post(f"/api/cases/{cid}/close", json={
        "verdict": "ADJUSTED", "root_cause": "unbundled coding", "recovered": 5000, "prevented": 7500}).json()
    assert r["status"] == "CLOSED" and r["verdict"] == "ADJUSTED"
    assert r["rand_recovered"] == 5000.0 and r["rand_prevented"] == 7500.0 and r["closed_at"]


def test_illegal_transition_is_409():
    _login("handler")
    cid = _open()["id"]
    client.post(f"/api/cases/{cid}/close", json={"verdict": "NO_ACTION"})
    assert client.post(f"/api/cases/{cid}/close").status_code == 409   # already CLOSED


def test_wrong_actor_is_403():
    _login("handler")
    cid = _open("REVIEW")["id"]
    client.post("/api/auth/logout")
    _login("medical")                                                 # not HANDLER/INVESTIGATOR
    assert client.post(f"/api/cases/{cid}/assign").status_code == 403


def test_lane_ownership_gate_is_409():
    _login("handler")
    cid = _open("CLAWBACK")["id"]                                     # opening is permissive
    assert client.post(f"/api/cases/{cid}/assign").status_code == 409  # CLAWBACK owned by INVESTIGATOR
    client.post("/api/auth/logout")
    _login("investigator")
    assert client.post(f"/api/cases/{cid}/assign").json()["status"] == "IN_REVIEW"


def test_escalation_routes_close_to_investigator_only():
    _login("handler")
    cid = _open("REVIEW")["id"]
    assert client.post(f"/api/cases/{cid}/escalate").json()["status"] == "ESCALATED"
    # once ESCALATED the INVESTIGATOR transition role governs — HANDLER may not close it
    assert client.post(f"/api/cases/{cid}/close", json={"verdict": "CLEARED"}).status_code == 403
    client.post("/api/auth/logout")
    _login("investigator")
    assert client.post(f"/api/cases/{cid}/close",
                       json={"verdict": "CONFIRMED_FRAUD"}).json()["status"] == "CLOSED"


def test_invalid_lane_priority_verdict_are_409():
    _login("handler")
    assert client.post("/api/cases", json={"lane": "NOPE", "reason": "x"}).status_code == 409
    assert client.post("/api/cases", json={"lane": "REVIEW", "priority": 9}).status_code == 409
    cid = _open("REVIEW")["id"]
    assert client.post(f"/api/cases/{cid}/close", json={"verdict": "BOGUS"}).status_code == 409


def test_notes_are_append_only_and_ordered():
    _login("handler")
    cid = _open("REVIEW")["id"]
    client.post(f"/api/cases/{cid}/notes", json={"body": "first look"})
    client.post(f"/api/cases/{cid}/notes", json={"body": "second look"})
    ns = client.get(f"/api/cases/{cid}/notes").json()
    assert [n["body"] for n in ns] == ["first look", "second look"] and ns[0]["author"] == "handler"


def test_analytics_and_labels_reflect_closed_cases():
    _login("investigator")
    cid = _open("BLOCK", "accident ring", priority=1, rand=90000.0)["id"]
    client.post(f"/api/cases/{cid}/close", json={
        "verdict": "CONFIRMED_FRAUD", "root_cause": "staged accident", "prevented": 90000})
    a = client.get("/api/cases/analytics").json()
    assert a["by_verdict"].get("CONFIRMED_FRAUD", 0) >= 1 and a["rand_prevented"] >= 90000.0
    labels = client.get("/api/cases/labels").json()
    assert any(lbl["case_id"] == cid and lbl["verdict"] == "CONFIRMED_FRAUD" for lbl in labels)


def test_transition_writes_actor_stamped_history():
    from sqlalchemy import select
    from server import models
    from server.db import SessionLocal
    _login("handler")
    cid = _open("REVIEW")["id"]
    client.post(f"/api/cases/{cid}/assign")
    with SessionLocal() as db:
        rows = list(db.scalars(select(models.TransitionLog).where(
            models.TransitionLog.entity_type == "case",
            models.TransitionLog.entity_id == str(cid))))
    assert any(r.action == "assign" and r.actor == "handler" and r.to_state == "IN_REVIEW"
               for r in rows)


def test_cases_require_auth():
    client.post("/api/auth/logout")
    assert client.get("/api/cases").status_code == 401
