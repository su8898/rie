"""State machines end-to-end — the full claim lifecycle + merits + offer persistence, plus the
enforcement failure modes (illegal transition 409, wrong actor 403, unmet gate 409)."""
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


def test_full_lifecycle_happy_path():
    _submit("R_lc1", "P_lc1", "CAS 8001/02/2026")
    assert client.get("/api/lifecycle/R_lc1").json()["stage"] == "LODGED"
    assert client.post("/api/lifecycle/R_lc1/validate").json()["stage"] == "VALIDATED"
    assert client.post("/api/lifecycle/R_lc1/open_merits").json()["stage"] == "MERITS"
    # accept_merits is gated until the merits determination is accepted
    assert client.post("/api/lifecycle/R_lc1/accept_merits").status_code == 409
    m = client.post("/api/merits/R_lc1/accept", json={"fault_pct": 25}).json()
    assert m["status"] == "ACCEPTED" and m["fault_pct"] == 25.0
    assert client.post("/api/lifecycle/R_lc1/accept_merits").json()["stage"] == "QUANTUM"
    # make_offer is gated until an offer is assembled
    assert client.post("/api/lifecycle/R_lc1/make_offer").status_code == 409
    offer = client.post("/api/offer/R_lc1",
                        json={"heads_input": {"loss_of_earnings": {"annual_losses": [100000]}}}).json()
    assert offer["status"] == "ASSEMBLED"
    assert offer["heads"]["past_medical"] == 375.0          # 500 apportioned 25%
    assert offer["heads"]["loss_of_earnings"]["total"] == 75000.0
    assert offer["offer_total"] == 75375.0
    assert client.post("/api/lifecycle/R_lc1/make_offer").json()["stage"] == "OFFER_MADE"
    assert client.post("/api/lifecycle/R_lc1/settle").json()["stage"] == "SETTLED"
    # pay requires ADMIN
    assert client.post("/api/lifecycle/R_lc1/pay").status_code == 403
    _login("admin")
    assert client.post("/api/lifecycle/R_lc1/pay").json()["stage"] == "PAID"
    assert client.post("/api/lifecycle/R_lc1/finalize").json()["stage"] == "FINALIZED"
    _login("handler")
    hist = client.get("/api/lifecycle/R_lc1").json()["history"]
    assert [x["to"] for x in hist] == ["VALIDATED", "MERITS", "QUANTUM", "OFFER_MADE",
                                       "SETTLED", "PAID", "FINALIZED"]
    assert hist[-1]["actor"] == "admin"


def test_illegal_transition_409():
    _submit("R_lc2", "P_lc2", "CAS 8002/02/2026")
    assert client.post("/api/lifecycle/R_lc2/settle").status_code == 409   # no 'settle' from LODGED


def test_validate_gate_blocks_incomplete_s24():
    _submit("R_lc3", "P_lc3", "CAS 8003/02/2026",
            documents={"RAF1": True, "OAR": False, "ID": True, "BANK": True})
    assert client.post("/api/lifecycle/R_lc3/validate").status_code == 409  # OAR missing → gate


def test_merits_reject_holds_offer():
    _submit("R_lc4", "P_lc4", "CAS 8004/02/2026")
    m = client.post("/api/merits/R_lc4/reject", json={"ground": "SOLE_NEGLIGENCE"}).json()
    assert m["status"] == "REJECTED" and m["ground"] == "SOLE_NEGLIGENCE"
    offer = client.post("/api/offer/R_lc4", json={}).json()
    assert offer["status"] == "HELD"
    assert offer["offer_total"] == 0.0
    assert "held_for_merits" in offer["gated_by"]


def test_merits_appeal_path():
    _submit("R_lc6", "P_lc6", "CAS 8006/02/2026")
    client.post("/api/merits/R_lc6/reject", json={"ground": "S19_EXCLUSION"})
    _login("legal")
    assert client.post("/api/merits/R_lc6/appeal").json()["status"] == "APPEALED"
    assert client.post("/api/merits/R_lc6/accept", json={"fault_pct": 0}).json()["status"] == "ACCEPTED"


def test_merits_wrong_actor_403():
    _submit("R_lc5", "P_lc5", "CAS 8005/02/2026")
    _login("investigator")
    assert client.post("/api/merits/R_lc5/accept", json={"fault_pct": 0}).status_code == 403
