"""The per-claim workflow aggregation — one call returns every machine's state + actions."""
from __future__ import annotations

import test_api  # noqa: F401  (sets RIE_DATABASE_URL + imports the app first)
from fastapi.testclient import TestClient
from server.main import app

client = TestClient(app)

CLAIM = {
    "claim_type": "PERSONAL", "accident_date": "2026-02-01", "lodged_on": "2026-03-01",
    "today": "2026-07-05", "payee_verified": True,
    "documents": {"RAF1": True, "OAR": True, "ID": True, "BANK": True},
    "lines": [{"kind": "TARIFF", "code": "0190", "qty": 1, "amount": 500.0,
               "service_date": "2026-03-01", "provider_id": "PR1", "dx": "S72"}],
}


def _login(user="handler"):
    assert client.post("/api/auth/login", json={"username": user, "password": user}).status_code == 200


def test_workflow_aggregates_all_machines():
    _login("handler")
    cid = "R_wf1"
    client.post("/api/claims", json={**CLAIM, "claim_id": cid, "party_token": "P_wf1",
                                     "case_number_raw": "CAS 9200/02/2026"})
    wf = client.get(f"/api/claims/{cid}/workflow").json()
    assert wf["lifecycle"]["stage"] == "LODGED"
    assert "validate" in wf["lifecycle"]["actions"]
    assert wf["merits"]["status"] == "PENDING"
    assert wf["offer"] is None
    assert wf["serious_injury"] == [] and wf["undertakings"] == [] and wf["litigation"] == []

    _login("legal")
    client.post("/api/litigation", json={"claim_id": cid})
    _login("medical")
    si = client.post("/api/serious-injury", json={"claim_id": cid, "list_match": True}).json()
    client.post("/api/undertakings", json={"claim_id": cid, "origin": "SETTLEMENT", "scope_dx": ["S72"]})

    _login("handler")
    wf = client.get(f"/api/claims/{cid}/workflow").json()
    assert len(wf["serious_injury"]) == 1 and wf["serious_injury"][0]["id"] == si["id"]
    assert "accept" in wf["serious_injury"][0]["actions"]
    assert len(wf["undertakings"]) == 1 and wf["undertakings"][0]["status"] == "ISSUED"
    assert "activate" in wf["undertakings"][0]["actions"]
    assert len(wf["litigation"]) == 1 and wf["litigation"][0]["status"] == "SUMMONS_SERVED"
