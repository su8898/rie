"""Litigation state machine end-to-end — the full matter lifecycle (plead → set_trial → settle →
order_paid → close), the missed-pleadings default-judgment branch, plus the enforcement failure
modes (illegal transition 409, wrong actor 403) and the actor-stamped history."""
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
    assert client.post("/api/auth/login", json={"username": user, "password": user}).status_code == 200


def _submit(cid, party, cas, **kw):
    _login("handler")
    assert client.post("/api/claims", json={**PERSONAL, "claim_id": cid, "party_token": party,
                                            "case_number_raw": cas, **kw}).status_code == 200


def _open_litigation(cid, party, cas):
    """Submit a PERSONAL claim (handler) then open the litigation matter (legal); return its id."""
    _submit(cid, party, cas)
    _login("legal")
    r = client.post("/api/litigation", json={"claim_id": cid})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["status"] == "SUMMONS_SERVED"
    assert j["default_judgment"] is False
    return j["id"]


def test_full_litigation_happy_path():
    lit_id = _open_litigation("R_lit1", "P_lit1", "CAS 8301/02/2026")
    base = f"/api/litigation/{lit_id}"
    assert client.get(base).json()["status"] == "SUMMONS_SERVED"
    _login("legal")
    assert client.post(f"{base}/plead").json()["status"] == "PLEADINGS"
    assert client.post(f"{base}/set_trial").json()["status"] == "TRIAL_SET"
    assert client.post(f"{base}/settle").json()["status"] == "SETTLED"
    # order_paid requires ADMIN
    assert client.post(f"{base}/order_paid").status_code == 403
    _login("admin")
    assert client.post(f"{base}/order_paid").json()["status"] == "ORDER_PAID"
    assert client.post(f"{base}/close").json()["status"] == "CLOSED"
    # default_judgment untouched on the settlement path
    assert client.get(base).json()["default_judgment"] is False


def test_default_judgment_path():
    lit_id = _open_litigation("R_lit2", "P_lit2", "CAS 8302/02/2026")
    base = f"/api/litigation/{lit_id}"
    _login("legal")
    assert client.post(f"{base}/plead").json()["status"] == "PLEADINGS"
    j = client.post(f"{base}/default_judgment").json()
    assert j["status"] == "JUDGMENT"
    assert j["default_judgment"] is True
    # JUDGMENT → ORDER_PAID → CLOSED
    _login("admin")
    assert client.post(f"{base}/order_paid").json()["status"] == "ORDER_PAID"
    assert client.post(f"{base}/close").json()["status"] == "CLOSED"
    # flag persists on read-back
    assert client.get(base).json()["default_judgment"] is True


def test_illegal_transition_409():
    lit_id = _open_litigation("R_lit3", "P_lit3", "CAS 8303/02/2026")
    _login("legal")
    # no 'settle' from SUMMONS_SERVED
    assert client.post(f"/api/litigation/{lit_id}/settle").status_code == 409


def test_wrong_actor_403():
    lit_id = _open_litigation("R_lit4", "P_lit4", "CAS 8304/02/2026")
    _login("handler")                        # handler is not a LEGAL lane
    assert client.post(f"/api/litigation/{lit_id}/plead").status_code == 403


def test_create_requires_legal():
    _submit("R_lit5", "P_lit5", "CAS 8305/02/2026")
    _login("handler")                        # create is LEGAL-only (ADMIN superuser)
    assert client.post("/api/litigation", json={"claim_id": "R_lit5"}).status_code == 403


def test_missing_litigation_404():
    _login("legal")
    assert client.get("/api/litigation/999999").status_code == 404


def test_history_recorded():
    lit_id = _open_litigation("R_lit6", "P_lit6", "CAS 8306/02/2026")
    base = f"/api/litigation/{lit_id}"
    _login("legal")
    client.post(f"{base}/plead")
    client.post(f"{base}/set_trial")
    client.post(f"{base}/settle")
    _login("admin")
    client.post(f"{base}/order_paid")
    client.post(f"{base}/close")
    hist = client.get(base).json()["history"]
    assert [x["to"] for x in hist] == ["PLEADINGS", "TRIAL_SET", "SETTLED", "ORDER_PAID", "CLOSED"]
    assert hist[0]["action"] == "plead" and hist[0]["actor"] == "legal"
    assert hist[-1]["actor"] == "admin" and hist[-1]["role"] == "ADMIN"
