"""Payment batches — assembly, segregation of duties, eligibility/payee gates, and the
settlement→lifecycle-PAID advance."""
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
               "service_date": "2026-03-01", "provider_id": "PR1", "dx": "S72"}],
}
PERSONAL = {**SUPPLIER, "claim_type": "PERSONAL",
            "documents": {"RAF1": True, "OAR": True, "ID": True, "BANK": True}}


def _login(user="handler"):
    assert client.post("/api/auth/login", json={"username": user, "password": user}).status_code == 200


def _submit(base, cid, party, cas, **kw):
    _login("handler")
    assert client.post("/api/claims",
                       json={**base, "claim_id": cid, "party_token": party,
                             "case_number_raw": cas, **kw}).status_code == 200


def test_full_batch_happy_path():
    _submit(SUPPLIER, "R_pay1", "P_pay1", "CAS 9300/02/2026")           # eligible supplier
    _login("handler")
    b = client.post("/api/payments/batches", json={"note": "run 1"}).json()
    bid = b["id"]
    assert b["status"] == "OPEN" and b["created_by"] == "handler"
    b = client.post(f"/api/payments/batches/{bid}/instructions",
                    json={"claim_id": "R_pay1", "source": "SUPPLIER"}).json()
    assert b["total"] == 500.0 and b["instructions"][0]["source"] == "SUPPLIER"
    # handler cannot approve (role), and the assembler cannot approve (SoD) — admin approves
    assert client.post(f"/api/payments/batches/{bid}/approve").status_code == 403  # handler role
    _login("admin")
    assert client.post(f"/api/payments/batches/{bid}/approve").json()["status"] == "APPROVED"
    b = client.post(f"/api/payments/batches/{bid}/pay").json()
    assert b["status"] == "PAID"
    assert b["instructions"][0]["paid"] is True
    events = [e["event"] for e in b["events"]]
    assert events == ["CREATED", "INSTRUCTION_ADDED", "APPROVED", "PAID"]
    assert b["paid_by"] == "admin"


def test_segregation_of_duties_same_actor():
    _submit(SUPPLIER, "R_pay2", "P_pay2", "CAS 9301/02/2026")
    _login("admin")                                                     # admin assembles...
    bid = client.post("/api/payments/batches", json={}).json()["id"]
    client.post(f"/api/payments/batches/{bid}/instructions",
                json={"claim_id": "R_pay2", "source": "SUPPLIER"})
    r = client.post(f"/api/payments/batches/{bid}/approve")             # ...and tries to approve
    assert r.status_code == 403
    assert "segregation of duties" in r.json()["detail"].lower()


def test_cannot_approve_empty_batch():
    _login("handler")
    bid = client.post("/api/payments/batches", json={}).json()["id"]
    _login("admin")
    assert client.post(f"/api/payments/batches/{bid}/approve").status_code == 409


def test_eligibility_gate_blocks_ineligible_claim():
    _submit(PERSONAL, "R_pay3", "P_pay3", "CAS 9302/02/2026")           # personal, merits pending → not eligible
    _login("handler")
    bid = client.post("/api/payments/batches", json={}).json()["id"]
    r = client.post(f"/api/payments/batches/{bid}/instructions",
                    json={"claim_id": "R_pay3", "source": "SUPPLIER"})
    assert r.status_code == 409 and "eligible" in r.json()["detail"].lower()


def test_payee_verification_gate():
    _submit(SUPPLIER, "R_pay4", "P_pay4", "CAS 9303/02/2026", payee_verified=False)
    _login("handler")
    bid = client.post("/api/payments/batches", json={}).json()["id"]
    r = client.post(f"/api/payments/batches/{bid}/instructions",
                    json={"claim_id": "R_pay4", "source": "SUPPLIER"})
    assert r.status_code == 409 and "PAYEE_UNVERIFIED" in r.json()["detail"]


def test_illegal_pay_before_approve():
    _submit(SUPPLIER, "R_pay5", "P_pay5", "CAS 9304/02/2026")
    _login("handler")
    bid = client.post("/api/payments/batches", json={}).json()["id"]
    client.post(f"/api/payments/batches/{bid}/instructions",
                json={"claim_id": "R_pay5", "source": "SUPPLIER"})
    _login("admin")
    assert client.post(f"/api/payments/batches/{bid}/pay").status_code == 409  # not APPROVED


def test_settlement_payment_advances_lifecycle_to_paid():
    _submit(PERSONAL, "R_pay6", "P_pay6", "CAS 9305/02/2026")
    _login("handler")
    for action in ("validate", "open_merits"):
        client.post(f"/api/lifecycle/R_pay6/{action}")
    client.post("/api/merits/R_pay6/accept", json={"fault_pct": 0})
    client.post("/api/lifecycle/R_pay6/accept_merits")
    client.post("/api/offer/R_pay6", json={})                          # ASSEMBLED (merits accepted)
    client.post("/api/lifecycle/R_pay6/make_offer")
    client.post("/api/lifecycle/R_pay6/settle")                        # SETTLED
    assert client.get("/api/lifecycle/R_pay6").json()["stage"] == "SETTLED"
    bid = client.post("/api/payments/batches", json={}).json()["id"]
    client.post(f"/api/payments/batches/{bid}/instructions",
                json={"claim_id": "R_pay6", "source": "SETTLEMENT", "amount": 500.0})
    _login("admin")
    client.post(f"/api/payments/batches/{bid}/approve")
    assert client.post(f"/api/payments/batches/{bid}/pay").json()["status"] == "PAID"
    _login("handler")
    assert client.get("/api/lifecycle/R_pay6").json()["stage"] == "PAID"   # advanced by the payment


def test_queue_lists_eligible_and_cancel():
    _submit(SUPPLIER, "R_pay7", "P_pay7", "CAS 9306/02/2026")
    _login("handler")
    ids = {row["claim_id"] for row in client.get("/api/payments/queue").json()}
    assert "R_pay7" in ids
    bid = client.post("/api/payments/batches", json={}).json()["id"]
    assert client.post(f"/api/payments/batches/{bid}/cancel").json()["status"] == "CANCELLED"
