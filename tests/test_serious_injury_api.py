"""Serious-injury (RAF 4) state machine end-to-end over HTTP — submit an assessment, RAF
accept/reject, HPCSA appeal → uphold/dismiss, plus the enforcement failure modes (illegal
transition 409, wrong actor 403) and the actor-stamped history."""
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
    """A PERSONAL claim must exist (submitted by a handler) before an SI record references it."""
    _login("handler")
    assert client.post("/api/claims", json={**PERSONAL, "claim_id": cid, "party_token": party,
                                            "case_number_raw": cas}).status_code == 200


def _create_si(claim_id, **kw):
    _login("medical")
    r = client.post("/api/serious-injury", json={"claim_id": claim_id, **kw})
    assert r.status_code == 200, r.text
    return r.json()


def test_accept_happy_path():
    _submit("R_si1", "P_si1", "CAS 8101/02/2026")
    si = _create_si("R_si1", list_match=True, wpi=35.0, narrative=False)
    assert si["status"] == "SUBMITTED"
    assert si["claim_id"] == "R_si1" and si["list_match"] is True and si["wpi"] == 35.0
    sid = si["id"]
    body = client.get(f"/api/serious-injury/{sid}").json()
    assert body["status"] == "SUBMITTED"
    assert sorted(body["actions"]) == ["accept", "reject"]
    accepted = client.post(f"/api/serious-injury/{sid}/accept").json()
    assert accepted["status"] == "RAF_ACCEPTED"
    # RAF_ACCEPTED is terminal for the accept branch — no further actions
    assert client.get(f"/api/serious-injury/{sid}").json()["actions"] == []


def test_reject_appeal_uphold():
    _submit("R_si2", "P_si2", "CAS 8102/02/2026")
    sid = _create_si("R_si2", list_match=False, wpi=None, narrative=True)["id"]
    assert client.post(f"/api/serious-injury/{sid}/reject").json()["status"] == "RAF_REJECTED"
    # appeal + uphold are the LEGAL lane
    _login("legal")
    assert client.post(f"/api/serious-injury/{sid}/appeal").json()["status"] == "HPCSA_APPEAL"
    assert client.post(f"/api/serious-injury/{sid}/uphold").json()["status"] == "UPHELD"


def test_reject_appeal_dismiss():
    _submit("R_si3", "P_si3", "CAS 8103/02/2026")
    sid = _create_si("R_si3")["id"]
    assert client.post(f"/api/serious-injury/{sid}/reject").json()["status"] == "RAF_REJECTED"
    _login("legal")
    assert client.post(f"/api/serious-injury/{sid}/appeal").json()["status"] == "HPCSA_APPEAL"
    assert client.post(f"/api/serious-injury/{sid}/dismiss").json()["status"] == "DISMISSED"


def test_illegal_transition_409():
    _submit("R_si4", "P_si4", "CAS 8104/02/2026")
    sid = _create_si("R_si4")["id"]
    assert client.post(f"/api/serious-injury/{sid}/accept").json()["status"] == "RAF_ACCEPTED"
    # no 'accept' from RAF_ACCEPTED
    assert client.post(f"/api/serious-injury/{sid}/accept").status_code == 409


def test_wrong_actor_403():
    _submit("R_si5", "P_si5", "CAS 8105/02/2026")
    sid = _create_si("R_si5")["id"]
    _login("handler")                                  # not the MEDICAL_OFFICER lane
    assert client.post(f"/api/serious-injury/{sid}/accept").status_code == 403


def test_create_requires_medical_officer():
    _submit("R_si6", "P_si6", "CAS 8106/02/2026")
    _login("handler")                                  # create is MEDICAL_OFFICER-only
    assert client.post("/api/serious-injury",
                       json={"claim_id": "R_si6"}).status_code == 403


def test_missing_record_404():
    _login("medical")
    assert client.get("/api/serious-injury/999999").status_code == 404


def test_history_recorded():
    _submit("R_si7", "P_si7", "CAS 8107/02/2026")
    sid = _create_si("R_si7")["id"]
    client.post(f"/api/serious-injury/{sid}/reject")
    _login("legal")
    client.post(f"/api/serious-injury/{sid}/appeal")
    client.post(f"/api/serious-injury/{sid}/dismiss")
    hist = client.get(f"/api/serious-injury/{sid}").json()["history"]
    assert [x["to"] for x in hist] == ["RAF_REJECTED", "HPCSA_APPEAL", "DISMISSED"]
    assert [x["action"] for x in hist] == ["reject", "appeal", "dismiss"]
    assert hist[0]["actor"] == "medical" and hist[0]["role"] == "MEDICAL_OFFICER"
    assert hist[-1]["actor"] == "legal" and hist[-1]["role"] == "LEGAL"
