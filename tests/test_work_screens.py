"""Read models and corrections behind the work screens: case and dispute worklists, editing an
open item, each item's history, the notification worklist and the dashboard's work summary."""
from __future__ import annotations

import uuid

import test_api  # noqa: F401  (sets RIE_DATABASE_URL + imports the app first)
from fastapi.testclient import TestClient
from server.main import app

client = TestClient(app)

SUPPLIER = {
    "claim_type": "SUPPLIER", "accident_date": "2026-02-01", "lodged_on": "2026-03-01",
    "today": "2026-07-05", "payee_verified": True,
    "documents": {"RAF2": True, "OAR": True, "INVOICES": True, "BANK": True},
    "lines": [{"kind": "TARIFF", "code": "0190", "qty": 1, "amount": 500.0,
               "service_date": "2026-03-01", "provider_id": "PR_WRK", "dx": "S72"}],
}


def _login(user="handler"):
    assert client.post("/api/auth/login", json={"username": user, "password": user}).status_code == 200


def _claim(cid):
    _login("handler")
    r = client.post("/api/claims", json={**SUPPLIER, "claim_id": cid, "party_token": f"P_{cid}",
                                         "case_number_raw": "CAS 9700/02/2026"})
    assert r.status_code == 200, r.text


def _case(tag, **kw):
    body = {"lane": "REVIEW", "reason": f"wrk-{tag} check", "priority": 3, "rand_at_stake": 100.0, **kw}
    return client.post("/api/cases", json=body).json()


def test_case_worklist_filters_counts_sorts_and_pages():
    tag = uuid.uuid4().hex[:8]
    _login("handler")
    a = _case(tag, priority=1, rand_at_stake=900.0)
    b = _case(tag, priority=4, rand_at_stake=50.0)
    c = _case(tag, lane="BLOCK", priority=2)
    client.post(f"/api/cases/{a['id']}/assign")
    client.post(f"/api/cases/{b['id']}/close", json={"verdict": "CLEARED"})
    get = lambda **p: client.get("/api/cases/search", params={"q": f"wrk-{tag}", **p}).json()

    res = get()
    assert res["total"] == 3 and [r["id"] for r in res["rows"]] == [c["id"], b["id"], a["id"]]
    assert res["counts"] == {"OPEN": 1, "IN_REVIEW": 1, "ESCALATED": 0, "CLOSED": 1, "OVERDUE": 0, "MINE": 1}
    assert [r["id"] for r in get(status="CLOSED")["rows"]] == [b["id"]]
    assert get(status="CLOSED")["counts"]["OPEN"] == 1                     # counts ignore the status filter
    assert [r["id"] for r in get(open_only="true")["rows"]] == [c["id"], a["id"]]
    assert [r["id"] for r in get(mine="true")["rows"]] == [a["id"]]
    assert [r["id"] for r in get(lane="BLOCK")["rows"]] == [c["id"]]
    assert [r["id"] for r in get(sort="priority", direction="asc")["rows"]] == [a["id"], c["id"], b["id"]]
    assert [r["id"] for r in get(sort="stake")["rows"]][0] == a["id"]
    assert [r["id"] for r in get(limit=1, offset=1)["rows"]] == [b["id"]]
    assert client.get("/api/cases/search", params={"q": f"#{a['id']}"}).json()["rows"][0]["id"] == a["id"]
    assert client.get("/api/cases/search", params={"sort": "nope"}).status_code == 422
    assert TestClient(app).get("/api/cases/search").status_code == 401


def test_open_case_can_be_corrected_and_the_change_is_in_its_history():
    tag = uuid.uuid4().hex[:8]
    _login("handler")
    c = _case(tag, priority=3)
    cid = c["id"]
    r = client.patch(f"/api/cases/{cid}", json={"priority": 1, "reason": "corrected reason", "rand_at_stake": 250})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["priority"] == 1 and out["sla_days"] == 1 and out["reason"] == "corrected reason"
    assert out["rand_at_stake"] == 250.0 and out["due_at"] < c["due_at"]   # a tighter deadline
    hist = client.get(f"/api/cases/{cid}/history").json()
    assert hist[0]["action"] == "edit" and hist[0]["actor"] == "handler"
    assert hist[0]["detail"]["changes"]["priority"] == {"from": 3, "to": 1}
    assert set(hist[0]["detail"]["changes"]) == {"priority", "reason", "rand_at_stake"}
    n = len(hist)
    client.patch(f"/api/cases/{cid}", json={"priority": 1})                # nothing changes, nothing logged
    assert len(client.get(f"/api/cases/{cid}/history").json()) == n

    assert client.patch(f"/api/cases/{cid}", json={"priority": 9}).status_code == 409
    assert client.patch(f"/api/cases/{cid}", json={"reason": "  "}).status_code == 409
    assert client.patch(f"/api/cases/{cid}", json={"rand_at_stake": -1}).status_code == 409
    _login("legal")                                                        # not the lane's owner
    assert client.patch(f"/api/cases/{cid}", json={"priority": 2}).status_code == 403
    _login("handler")
    client.post(f"/api/cases/{cid}/close", json={"verdict": "CLEARED"})
    assert client.patch(f"/api/cases/{cid}", json={"priority": 2}).status_code == 409   # closed is a record
    actions = [h["action"] for h in client.get(f"/api/cases/{cid}/history").json()]
    assert actions == ["close", "edit"]
    assert client.patch("/api/cases/99999999", json={"priority": 2}).status_code == 409


def test_dispute_worklist_edit_and_history():
    tag = uuid.uuid4().hex[:8]
    cid = f"R_WRK_{tag}"
    _claim(cid)
    lodge = lambda subject, by: client.post("/api/disputes", json={
        "claim_id": cid, "subject": subject, "raised_by": by, "grounds": f"wrk-{tag} grounds"}).json()
    a, b = lodge("TARIFF", "PROVIDER"), lodge("MERITS", "CLAIMANT")
    client.post(f"/api/disputes/{a['id']}/reconsider")
    client.post(f"/api/disputes/{b['id']}/withdraw")
    get = lambda **p: client.get("/api/disputes/search", params={"q": f"wrk-{tag}", **p}).json()

    res = get()
    assert res["total"] == 2 and [r["id"] for r in res["rows"]] == [b["id"], a["id"]]
    assert res["counts"]["OPEN"] == 1 and res["counts"]["UNDER_RECONSIDERATION"] == 1
    assert res["counts"]["WITHDRAWN"] == 1 and res["counts"]["OVERDUE"] == 0
    assert [r["id"] for r in get(open_only="true")["rows"]] == [a["id"]]
    assert [r["id"] for r in get(subject="MERITS")["rows"]] == [b["id"]]
    assert [r["id"] for r in get(raised_by="PROVIDER")["rows"]] == [a["id"]]
    assert [r["id"] for r in get(channel="INTERNAL")["rows"]] == [a["id"]]
    assert client.get("/api/disputes/search", params={"claim_id": cid}).json()["total"] == 2
    assert [r["id"] for r in get(sort="deadline", direction="asc", limit=1)["rows"]] == [a["id"]]

    r = client.patch(f"/api/disputes/{a['id']}", json={"grounds": "the tariff code was applied to the wrong discipline"})
    assert r.status_code == 200 and r.json()["grounds"].startswith("the tariff code")
    hist = client.get(f"/api/disputes/{a['id']}/history").json()
    assert [h["action"] for h in hist] == ["edit", "reconsider"]
    assert hist[0]["detail"]["changes"]["grounds"]["from"] == f"wrk-{tag} grounds"
    assert client.patch(f"/api/disputes/{a['id']}", json={"grounds": ""}).status_code == 409
    assert client.patch(f"/api/disputes/{b['id']}", json={"grounds": "late"}).status_code == 409   # withdrawn
    _login("investigator")
    assert client.patch(f"/api/disputes/{a['id']}", json={"grounds": "x"}).status_code == 403


def test_notification_worklist_and_work_summary():
    _login("handler")
    res = client.get("/api/notifications/search", params={"limit": 5}).json()
    assert set(res) == {"rows", "total", "counts", "events"}
    assert set(res["counts"]) == {"PENDING", "SENT", "FAILED", "SUPPRESSED"}
    assert res["total"] == sum(res["counts"].values()) and len(res["rows"]) <= 5
    if res["rows"]:
        n = res["rows"][0]
        one = client.get("/api/notifications/search", params={"claim_id": n["claim_id"], "status": n["status"]}).json()
        assert one["total"] >= 1 and all(r["claim_id"] == n["claim_id"] for r in one["rows"])
    assert client.get("/api/notifications/search", params={"q": "no-such-thing-zzz"}).json()["total"] == 0

    tag = uuid.uuid4().hex[:8]
    before = client.get("/api/dashboard/work").json()
    c = _case(tag)
    client.post(f"/api/cases/{c['id']}/assign")
    after = client.get("/api/dashboard/work").json()
    assert after["cases"]["open"] == before["cases"]["open"] + 1
    assert after["cases"]["mine"] == before["cases"]["mine"] + 1
    assert set(after) == {"cases", "disputes", "payments", "notifications"}
    assert after["payments"]["ready"] >= 0 and after["payments"]["ready_amount"] >= 0
    assert TestClient(app).get("/api/dashboard/work").status_code == 401


def test_claim_workflow_history_spans_every_machine():
    cid = f"R_WFH_{uuid.uuid4().hex[:8]}"
    _login("handler")
    r = client.post("/api/claims", json={**SUPPLIER, "claim_type": "PERSONAL", "claim_id": cid, "party_token": f"P_{cid}",
                                         "case_number_raw": "CAS 9701/02/2026",
                                         "documents": {"RAF1": True, "OAR": True, "ID": True, "BANK": True}})
    assert r.status_code == 200, r.text
    assert client.get(f"/api/claims/{cid}/workflow/history").json() == []
    for action in ("validate", "open_merits"):
        assert client.post(f"/api/lifecycle/{cid}/{action}").status_code == 200
    assert client.post(f"/api/merits/{cid}/accept", json={"fault_pct": 20}).status_code == 200
    u = client.post("/api/undertakings", json={"claim_id": cid, "origin": "SETTLEMENT", "scope_dx": ["S72"]}).json()
    assert client.post(f"/api/undertakings/{u['id']}/state/activate").status_code == 200

    hist = client.get(f"/api/claims/{cid}/workflow/history").json()
    assert [(h["area"], h["action"]) for h in hist] == [
        ("undertaking", "activate"), ("merits", "accept"),
        ("claim_lifecycle", "open_merits"), ("claim_lifecycle", "validate")]
    assert hist[0]["ref"] == str(u["id"]) and hist[0]["actor"] == "handler" and hist[0]["to_state"] == "ACTIVE"
    assert hist[-1]["from_state"] == "LODGED" and hist[-1]["to_state"] == "VALIDATED"
    assert TestClient(app).get(f"/api/claims/{cid}/workflow/history").status_code == 401


def test_an_invoice_is_never_approved_for_more_than_was_billed():
    cid = f"R_INV_{uuid.uuid4().hex[:8]}"
    _claim(cid)
    _login("medical")
    u = client.post("/api/undertakings", json={"claim_id": cid, "origin": "SETTLEMENT", "scope_dx": ["S72"]}).json()
    client.post(f"/api/undertakings/{u['id']}/state/activate")
    inv = client.post(f"/api/undertakings/{u['id']}/invoices", json={"billed": 800.0, "dx": "S72"}).json()
    for bad in (800.01, -1, "abc"):
        r = client.post(f"/api/undertakings/invoices/{inv['id']}/adjudicate", json={"approved": bad})
        assert r.status_code == 409, (bad, r.text)
    ok = client.post(f"/api/undertakings/invoices/{inv['id']}/adjudicate", json={"approved": 650})
    assert ok.status_code == 200 and ok.json()["payable"] == 650.0 and ok.json()["status"] == "ADJUDICATED"


def test_recovery_is_never_recorded_above_the_amount_paid():
    from server import models
    from server.db import SessionLocal
    with SessionLocal() as db:
        a = models.AuditQueue(claim_id="R_pay1", status="OPEN", reason="test", amount_at_stake=500.0,
                              amount_recovered=0.0, opened_by="investigator")
        db.add(a)
        db.commit()
        aid = a.id
    _login("investigator")
    assert client.post(f"/api/audit/{aid}/review").status_code == 200
    for bad in (500.01, -5, "abc"):
        assert client.post(f"/api/audit/{aid}/recover", json={"amount": bad}).status_code == 409, bad
    ok = client.post(f"/api/audit/{aid}/recover", json={"amount": 200})
    assert ok.status_code == 200 and ok.json()["amount_recovered"] == 200.0
    assert ok.json()["recovery_outcome"] == "RECOVERED_PARTIAL"
