"""Remittance advice (port of CIE's ERA) — issued per provider when a batch is paid, reconciled
line by line to the amount actually paid, and served to operators and over the rails channel."""
from __future__ import annotations

import time
import uuid
import xml.etree.ElementTree as ET

import pytest
import test_api  # noqa: F401  (sets RIE_DATABASE_URL + imports the app first)
from fastapi.testclient import TestClient
from sqlalchemy import select

from server import jws, models, remittance_service as svc
from server.db import SessionLocal
from server.main import app

ops = TestClient(app)                                    # the Fund's operators (session cookie)
provider = TestClient(app)                               # a provider system (JWS only, no session)
SECRET = "rie-rails-dev-secret"


def _login(user):
    assert ops.post("/api/auth/login", json={"username": user, "password": user}).status_code == 200


def _line(amount, provider_id, svc_date="2026-03-01", code="0190"):
    return {"kind": "TARIFF", "code": code, "qty": 1, "amount": amount, "service_date": svc_date,
            "provider_id": provider_id, "dx": "S72"}


def _submit(cid, party, cas, lines, **kw):
    _login("handler")
    r = ops.post("/api/claims", json={
        "claim_id": cid, "claim_type": "SUPPLIER", "party_token": party, "case_number_raw": cas,
        "accident_date": "2026-02-01", "lodged_on": "2026-03-01", "today": "2026-07-05",
        "payee_verified": True, "documents": {"RAF2": True, "OAR": True, "INVOICES": True, "BANK": True},
        "lines": lines, **kw})
    assert r.status_code == 200, r.text
    return r.json()


def _pay(*claim_ids) -> int:
    """Assemble (handler), approve (admin) and pay (treasury) a batch of supplier claims."""
    _login("handler")
    bid = ops.post("/api/payments/batches", json={}).json()["id"]
    for cid in claim_ids:
        r = ops.post(f"/api/payments/batches/{bid}/instructions", json={"claim_id": cid, "source": "SUPPLIER"})
        assert r.status_code == 200, r.text
    _login("admin")
    assert ops.post(f"/api/payments/batches/{bid}/approve").status_code == 200
    _login("treasury")
    assert ops.post(f"/api/payments/batches/{bid}/pay").json()["status"] == "PAID"
    return bid


def _sig(obj, exp=None, jti=True):
    header = {"alg": "HS256", "exp": exp or int(time.time()) + 300}
    if jti:
        header["jti"] = str(uuid.uuid4())
    return {"X-JWS-Signature": jws.sign_detached(header, obj, SECRET)}


@pytest.fixture(scope="module")
def paid():
    """Two claims, two providers, one paid batch. PR_REM_A bills on both claims."""
    _submit("R_REM_1", "P_REM_1", "CAS 9801/02/2026",
            [_line(800.0, "PR_REM_A"), _line(450.0, "PR_REM_A", "2026-03-05")])
    _submit("R_REM_2", "P_REM_2", "CAS 9802/02/2026",
            [_line(500.0, "PR_REM_A", "2026-03-09"), _line(650.0, "PR_REM_B", "2026-03-02")])
    bid = _pay("R_REM_1", "R_REM_2")
    _login("handler")
    rows = {r["provider_id"]: r for r in ops.get("/api/remittances").json() if r["batch_id"] == bid}
    return bid, rows


# ── allocation ───────────────────────────────────────────────────────────────
def test_allocation_reconciles_lines_to_the_payment_to_the_cent():
    assert svc.allocate([500.0, 300.0, 200.0], 1000.0) == [500.0, 300.0, 200.0]
    assert svc.allocate([500.0, 300.0, 200.0], 700.0) == [350.0, 210.0, 140.0]      # 30% apportioned
    assert svc.allocate([100.0, 100.0, 100.0], 100.0) == [33.33, 33.33, 33.34]      # residue on the last
    assert svc.allocate([0.0, 0.0], 50.0) == [0.0, 50.0]                            # nothing payable
    assert svc.allocate([], 50.0) == []


# ── issue ────────────────────────────────────────────────────────────────────
def test_paying_a_batch_issues_one_advice_per_provider(paid):
    bid, rows = paid
    assert set(rows) == {"PR_REM_A", "PR_REM_B"}
    a, b = rows["PR_REM_A"], rows["PR_REM_B"]
    assert (a["n_claims"], a["total_billed"], a["total_paid"], a["total_reduced"]) == (2, 1750.0, 1450.0, 300.0)
    assert (b["n_claims"], b["total_billed"], b["total_paid"], b["total_reduced"]) == (1, 650.0, 500.0, 150.0)
    assert (a["period_from"], a["period_to"]) == ("2026-03-01", "2026-03-09")
    assert a["status"] == "REMITTED" and a["payment_ref"] == f"BATCH-{bid}"
    assert a["ref"].startswith("ERA-") and a["invoice_ref"].startswith("INV-") and a["ref"] != b["ref"]
    # across providers the advices add up to exactly what the batch paid
    _login("handler")
    batch = next(x for x in ops.get("/api/payments/batches").json() if x["id"] == bid)
    assert a["total_paid"] + b["total_paid"] == batch["total"] == 1950.0


def test_advice_lists_each_claim_and_line_with_its_reason(paid):
    _bid, rows = paid
    _login("handler")
    d = ops.get(f"/api/remittances/{rows['PR_REM_A']['ref']}").json()
    assert [c["claim_id"] for c in d["claims"]] == ["R_REM_1", "R_REM_2"]
    first, second = d["claims"]
    assert (first["patient"], first["billed"], first["paid"], first["reduced"], first["outcome"]) == \
           ("P_REM_1", 1250.0, 950.0, 300.0, "REDUCED")
    assert first["lines"][0] == {
        "kind": "TARIFF", "code": "0190", "service_date": "2026-03-01", "billed": 800.0, "paid": 500.0,
        "reduced": 300.0, "reasons": ["BILLED_OVER_REFERENCE"],
        "reason_text": "Repriced to the reference tariff"}
    assert first["lines"][1]["reasons"] == [] and first["lines"][1]["paid"] == 450.0
    assert second["outcome"] == "PAID_IN_FULL" and len(second["lines"]) == 1     # only PR_REM_A's line


def test_issue_is_idempotent_and_guarded(paid):
    bid, _rows = paid
    _login("handler")
    assert ops.post(f"/api/remittances/issue/{bid}").status_code == 403          # ADMIN only
    _login("admin")
    assert ops.post(f"/api/remittances/issue/{bid}").json() == []               # nothing new to issue
    assert ops.post("/api/remittances/issue/999999").status_code == 404
    open_batch = ops.post("/api/payments/batches", json={}).json()["id"]
    r = ops.post(f"/api/remittances/issue/{open_batch}")
    assert r.status_code == 409 and "once the batch is paid" in r.json()["detail"]
    with SessionLocal() as db:
        assert len(list(db.scalars(select(models.Remittance).where(models.Remittance.batch_id == bid)))) == 2


def test_admin_can_issue_for_a_batch_paid_without_an_advice():
    _submit("R_REM_LATE", "P_REM_LATE", "CAS 9803/02/2026", [_line(500.0, "PR_REM_LATE")])
    bid = _pay("R_REM_LATE")
    with SessionLocal() as db:                           # as if paid before remittances existed
        rem = db.scalar(select(models.Remittance).where(models.Remittance.batch_id == bid))
        db.query(models.RemittanceLine).filter(models.RemittanceLine.remittance_id == rem.id).delete()
        db.delete(rem)
        db.commit()
    _login("admin")
    out = ops.post(f"/api/remittances/issue/{bid}").json()
    assert len(out) == 1 and out[0]["provider_id"] == "PR_REM_LATE" and out[0]["total_paid"] == 500.0


def test_apportioned_payment_is_spread_over_the_lines_and_explained():
    det = _submit("R_REM_APP", "P_REM_APP", "CAS 9804/02/2026",
                  [_line(500.0, "PR_REM_APP"), _line(300.0, "PR_REM_APP", "2026-03-03")], fault_pct=30.0)
    assert det["net_payable"] == 560.0                    # 70% of R800
    bid = _pay("R_REM_APP")
    _login("handler")
    ref = next(r["ref"] for r in ops.get("/api/remittances", params={"provider_id": "PR_REM_APP"}).json()
               if r["batch_id"] == bid)
    lines = ops.get(f"/api/remittances/{ref}").json()["claims"][0]["lines"]
    assert [(l["billed"], l["paid"], l["reduced"]) for l in lines] == [(500.0, 350.0, 150.0), (300.0, 210.0, 90.0)]
    assert all(l["reasons"] == ["PAYMENT_ADJUSTED"] for l in lines)
    assert lines[0]["reason_text"] == "Apportioned, or net of an earlier payment"


def test_review_signals_are_never_disclosed_on_an_advice():
    # the diagnosis does not fit the accident (a soft review signal) AND the line is over the tariff
    det = _submit("R_REM_DX", "P_REM_DX", "CAS 9805/02/2026", [_line(800.0, "PR_REM_DX")],
                  accident_dx_regions=["S06"])
    assert "DX_ACCIDENT_MISMATCH" in det["reasons"]
    bid = _pay("R_REM_DX")
    _login("handler")
    ref = next(r["ref"] for r in ops.get("/api/remittances", params={"provider_id": "PR_REM_DX"}).json()
               if r["batch_id"] == bid)
    assert ops.get(f"/api/remittances/{ref}").json()["claims"][0]["lines"][0]["reasons"] == ["BILLED_OVER_REFERENCE"]


def test_payments_to_claimants_are_not_remittances():
    _submit("R_REM_INT", "P_REM_INT", "CAS 9806/02/2026", [_line(500.0, "PR_REM_INT")])
    with SessionLocal() as db:
        batch = models.PaymentBatch(status="PAID", created_by="handler", approved_by="admin", paid_by="treasury")
        db.add(batch)
        db.flush()
        db.add(models.PaymentInstruction(batch_id=batch.id, claim_id="R_REM_INT", source="INTERIM",
                                         amount=100.0, paid=True))
        assert svc.issue_for_batch(db, batch, {"username": "treasury"}) == []
        db.rollback()


# ── operator formats ─────────────────────────────────────────────────────────
def test_operator_list_filters_and_needs_a_session(paid):
    _bid, rows = paid
    assert TestClient(app).get("/api/remittances").status_code == 401
    _login("handler")
    only_b = ops.get("/api/remittances", params={"provider_id": "PR_REM_B"}).json()
    assert [r["ref"] for r in only_b] == [rows["PR_REM_B"]["ref"]]
    hit = ops.get("/api/remittances", params={"provider_id": "PR_REM_A", "date_from": "2026-03-09"}).json()
    miss = ops.get("/api/remittances", params={"provider_id": "PR_REM_A", "date_from": "2026-03-10"}).json()
    early = ops.get("/api/remittances", params={"provider_id": "PR_REM_A", "date_to": "2026-02-28"}).json()
    assert len(hit) == 1 and miss == [] and early == []
    assert ops.get("/api/remittances/ERA-NOPE").status_code == 404


def test_xml_document_carries_the_same_totals(paid):
    _bid, rows = paid
    _login("handler")
    r = ops.get(f"/api/remittances/{rows['PR_REM_A']['ref']}/xml")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/xml")
    root = ET.fromstring(r.text)
    assert root.tag == "Remittance" and root.findtext("Header/Provider") == "PR_REM_A"
    assert root.findtext("Header/RemittanceRef") == rows["PR_REM_A"]["ref"]
    assert (root.findtext("Totals/Billed"), root.findtext("Totals/Paid"), root.findtext("Totals/Reduced")) == \
           ("1750.00", "1450.00", "300.00")
    claims = root.findall("Claims/Claim")
    assert [c.get("ref") for c in claims] == ["R_REM_1", "R_REM_2"]
    reason = claims[0].find("Line/Reason")
    assert reason.get("code") == "BILLED_OVER_REFERENCE" and reason.text == "Repriced to the reference tariff"
    assert sum(float(l.findtext("Paid")) for l in root.iter("Line")) == 1450.0


def test_print_page_is_static_escaped_markup(paid):
    _bid, rows = paid
    _login("handler")
    r = ops.get(f"/api/remittances/{rows['PR_REM_A']['ref']}/print")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert "default-src 'none'" in r.headers["content-security-policy"]
    assert rows["PR_REM_A"]["ref"] in r.text and "R1 450.00" in r.text and "<script" not in r.text
    assert "R300.00: Repriced to the reference tariff" in r.text


def test_hostile_identifiers_are_escaped_in_both_formats():
    evil = "PR<x>&\"'"
    _submit("R_REM_EVIL", "P_REM_EVIL", "CAS 9807/02/2026", [_line(500.0, evil)])
    bid = _pay("R_REM_EVIL")
    _login("handler")
    ref = next(r["ref"] for r in ops.get("/api/remittances").json() if r["batch_id"] == bid)
    assert ET.fromstring(ops.get(f"/api/remittances/{ref}/xml").text).findtext("Header/Provider") == evil
    page = ops.get(f"/api/remittances/{ref}/print").text
    assert "PR&lt;x&gt;&amp;" in page and "PR<x>" not in page


# ── the provider's access, over the rails channel ────────────────────────────
def test_provider_lists_fetches_and_acknowledges_over_the_rails(paid):
    _bid, rows = paid
    ref = rows["PR_REM_B"]["ref"]
    listed = provider.get("/rails/v1/remittances", params={"provider_id": "PR_REM_B"},
                          headers=_sig({"providerId": "PR_REM_B"}))
    assert listed.status_code == 200 and [r["ref"] for r in listed.json()] == [ref]
    full = provider.get(f"/rails/v1/remittances/{ref}", headers=_sig({"remittanceRef": ref})).json()
    assert full["total_paid"] == 500.0 and full["claims"][0]["lines"][0]["reasons"] == ["BILLED_OVER_REFERENCE"]
    as_xml = provider.get(f"/rails/v1/remittances/{ref}", params={"format": "xml"},
                          headers=_sig({"remittanceRef": ref}))
    assert ET.fromstring(as_xml.text).findtext("Totals/Paid") == "500.00"

    ack = provider.post(f"/rails/v1/remittances/{ref}/ack", headers=_sig({"remittanceRef": ref}))
    assert ack.status_code == 200 and ack.json()["status"] == "ACKNOWLEDGED"
    first_at = ack.json()["acknowledged_at"]
    again = provider.post(f"/rails/v1/remittances/{ref}/ack", headers=_sig({"remittanceRef": ref})).json()
    assert again["acknowledged_at"] == first_at             # idempotent


def test_rails_reads_are_not_public_and_signatures_are_bound_to_their_subject(paid):
    _bid, rows = paid
    ref = rows["PR_REM_A"]["ref"]
    assert provider.get("/rails/v1/remittances", params={"provider_id": "PR_REM_A"}).status_code == 401
    assert provider.get(f"/rails/v1/remittances/{ref}").status_code == 401
    # a signature for one provider does not open another's list, nor an expired one anything
    assert provider.get("/rails/v1/remittances", params={"provider_id": "PR_REM_A"},
                        headers=_sig({"providerId": "PR_REM_B"})).status_code == 401
    assert provider.get(f"/rails/v1/remittances/{ref}",
                        headers=_sig({"remittanceRef": ref}, exp=int(time.time()) - 5)).status_code == 401
    assert provider.post(f"/rails/v1/remittances/{ref}/ack").status_code == 401
    assert provider.get("/rails/v1/remittances/ERA-NOPE",
                        headers=_sig({"remittanceRef": "ERA-NOPE"})).status_code == 404
    assert provider.post("/rails/v1/remittances/ERA-NOPE/ack",
                         headers=_sig({"remittanceRef": "ERA-NOPE"})).status_code == 404
    _login("handler")                                       # an operator session may read the same route
    assert ops.get(f"/rails/v1/remittances/{ref}").status_code == 200


def test_summary_of_an_advice_without_service_dates():
    r = models.Remittance(ref="ERA-X", invoice_ref="INV-X", payment_ref="BATCH-0", batch_id=0,
                          provider_id="P", n_claims=0, total_billed=0.0, total_paid=0.0,
                          total_reduced=0.0, status="REMITTED")
    s = svc.summary(r)
    assert s["period_from"] is None and s["issued_at"] is None and s["acknowledged_at"] is None
    assert svc.to_xml({**s, "claims": []}).count("<From></From>") == 1
