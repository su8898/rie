"""Read models and corrections behind the payment screens: the run worklist, the enriched queue,
removing a claim from an open run, changing the note, and the remittance search."""
from __future__ import annotations

import test_api  # noqa: F401  (sets RIE_DATABASE_URL + imports the app first)
from fastapi.testclient import TestClient
from server.main import app

client = TestClient(app)

SUPPLIER = {
    "claim_type": "SUPPLIER", "accident_date": "2026-02-01", "lodged_on": "2026-03-01",
    "today": "2026-07-05", "payee_verified": True,
    "documents": {"RAF2": True, "OAR": True, "INVOICES": True, "BANK": True},
    "lines": [{"kind": "TARIFF", "code": "0190", "qty": 1, "amount": 500.0,
               "service_date": "2026-03-01", "provider_id": "PR_SCR", "dx": "S72"}],
}


def _login(user="handler"):
    assert client.post("/api/auth/login", json={"username": user, "password": user}).status_code == 200


def _submit(cid, party, cas, **kw):
    _login("handler")
    r = client.post("/api/claims", json={**SUPPLIER, "claim_id": cid, "party_token": party,
                                         "case_number_raw": cas, **kw})
    assert r.status_code == 200, r.text


def _queue_row(cid):
    return next(r for r in client.get("/api/payments/queue").json() if r["claim_id"] == cid)


def test_queue_says_how_and_whether_a_claim_can_be_paid():
    _submit("R_scr1", "P_scr1", "CAS 9601/02/2026")
    _submit("R_scr2", "P_scr2", "CAS 9602/02/2026", payee_verified=False)
    ok = _queue_row("R_scr1")
    assert ok["source"] == "SUPPLIER" and ok["amount"] == ok["net_payable"] and ok["blocked"] is None
    assert ok["claim_type"] == "SUPPLIER" and ok["providers"] == ["PR_SCR"] and ok["lodged_on"] == "2026-03-01"
    queued = {r["claim_id"] for r in client.get("/api/payments/queue").json()}
    assert "R_scr2" not in queued                              # an unverified payee is held, never queued

    bid = client.post("/api/payments/batches", json={}).json()["id"]
    client.post(f"/api/payments/batches/{bid}/instructions", json={"claim_id": "R_scr1", "source": "SUPPLIER"})
    held = _queue_row("R_scr1")
    assert held["blocked"] == "IN_BATCH" and held["in_batch"] == {"id": bid, "status": "OPEN"}
    client.post(f"/api/payments/batches/{bid}/cancel")
    assert _queue_row("R_scr1")["blocked"] is None             # a cancelled run frees the claim


def test_remove_instruction_and_note_only_while_open():
    _submit("R_scr3", "P_scr3", "CAS 9603/02/2026")
    _submit("R_scr4", "P_scr4", "CAS 9604/02/2026")
    b = client.post("/api/payments/batches", json={"note": "first"}).json()
    bid = b["id"]
    assert b["n_claims"] == 0 and b["created_at"] and b["paid_at"] is None and b["remittances"] == []
    for cid in ("R_scr3", "R_scr4"):
        b = client.post(f"/api/payments/batches/{bid}/instructions", json={"claim_id": cid, "source": "SUPPLIER"}).json()
    assert b["n_claims"] == 2 and b["instructions"][0]["providers"] == ["PR_SCR"]
    inst = next(i["id"] for i in b["instructions"] if i["claim_id"] == "R_scr4")

    assert client.delete(f"/api/payments/batches/{bid}/instructions/999999").status_code == 409
    b = client.delete(f"/api/payments/batches/{bid}/instructions/{inst}").json()
    assert [i["claim_id"] for i in b["instructions"]] == ["R_scr3"] and b["total"] == 500.0
    removed = b["events"][-1]
    assert removed["event"] == "INSTRUCTION_REMOVED" and removed["detail"]["claim_id"] == "R_scr4"
    assert _queue_row("R_scr4")["blocked"] is None             # back in the queue, payable again

    b = client.patch(f"/api/payments/batches/{bid}", json={"note": "  corrected  "}).json()
    assert b["note"] == "corrected" and b["events"][-1]["event"] == "NOTE_CHANGED"
    n = len(b["events"])
    assert len(client.patch(f"/api/payments/batches/{bid}", json={"note": "corrected"}).json()["events"]) == n

    _login("investigator")                                       # read-only roles cannot correct a run
    assert client.patch(f"/api/payments/batches/{bid}", json={"note": "x"}).status_code == 403
    _login("admin")
    client.post(f"/api/payments/batches/{bid}/approve")
    keep = client.get(f"/api/payments/batches/{bid}").json()["instructions"][0]["id"]
    assert client.delete(f"/api/payments/batches/{bid}/instructions/{keep}").status_code == 409
    assert client.patch(f"/api/payments/batches/{bid}", json={"note": "late"}).status_code == 409
    _login("treasury")
    b = client.post(f"/api/payments/batches/{bid}/pay").json()
    assert b["paid_at"] and [r["provider_id"] for r in b["remittances"]] == ["PR_SCR"]
    _login("handler")
    assert client.get("/api/claims/R_scr3").json()["payment"]["batch_id"] == bid


def test_run_worklist_filters_counts_and_pages():
    _submit("R_scr5", "P_scr5", "CAS 9605/02/2026")
    a = client.post("/api/payments/batches", json={"note": "worklist-alpha"}).json()["id"]
    c = client.post("/api/payments/batches", json={"note": "worklist-beta"}).json()["id"]
    client.post(f"/api/payments/batches/{a}/instructions", json={"claim_id": "R_scr5", "source": "SUPPLIER"})
    client.post(f"/api/payments/batches/{c}/cancel")

    res = client.get("/api/payments/runs", params={"q": "worklist-"}).json()
    assert res["total"] == 2 and [r["id"] for r in res["rows"]] == [c, a]          # newest first
    assert res["counts"] == {"OPEN": 1, "APPROVED": 0, "PAID": 0, "CANCELLED": 1}
    row = next(r for r in res["rows"] if r["id"] == a)
    assert row["n_claims"] == 1 and row["total"] == 500.0 and row["created_by"] == "handler"

    only_open = client.get("/api/payments/runs", params={"q": "worklist-", "status": "OPEN"}).json()
    assert [r["id"] for r in only_open["rows"]] == [a] and only_open["counts"]["CANCELLED"] == 1
    assert [r["id"] for r in client.get("/api/payments/runs", params={"q": "R_scr5"}).json()["rows"]] == [a]
    assert [r["id"] for r in client.get("/api/payments/runs", params={"q": f"#{c}"}).json()["rows"]] == [c]
    page = client.get("/api/payments/runs", params={"q": "worklist-", "limit": 1, "offset": 1, "direction": "asc"}).json()
    assert page["total"] == 2 and [r["id"] for r in page["rows"]] == [c]
    assert client.get("/api/payments/runs", params={"status": "NOPE"}).status_code == 422
    assert TestClient(app).get("/api/payments/runs").status_code == 401


def test_remittance_search():
    _submit("R_scr6", "P_scr6", "CAS 9606/02/2026")
    bid = client.post("/api/payments/batches", json={}).json()["id"]
    client.post(f"/api/payments/batches/{bid}/instructions", json={"claim_id": "R_scr6", "source": "SUPPLIER"})
    _login("admin")
    client.post(f"/api/payments/batches/{bid}/approve")
    _login("treasury")
    client.post(f"/api/payments/batches/{bid}/pay")

    res = client.get("/api/remittances/search", params={"batch_id": bid}).json()
    assert res["total"] == 1 and res["rows"][0]["provider_id"] == "PR_SCR"
    ref = res["rows"][0]["ref"]
    assert client.get("/api/remittances/search", params={"q": "R_scr6"}).json()["rows"][0]["ref"] == ref
    assert client.get("/api/remittances/search", params={"q": ref[-6:]}).json()["total"] == 1
    assert client.get("/api/remittances/search", params={"batch_id": bid, "status": "ACKNOWLEDGED"}).json()["total"] == 0
    assert client.get("/api/remittances/search", params={"batch_id": bid, "date_from": "2026-03-02"}).json()["total"] == 0
    assert client.get("/api/remittances/search", params={"status": "bad"}).status_code == 422
    assert client.get(f"/api/remittances/{ref}").json()["claims"][0]["claim_id"] == "R_scr6"
