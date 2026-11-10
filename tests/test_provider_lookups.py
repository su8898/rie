"""Provider lookups over the rails channel (port of CIE's interface-standard profiles): claim
status, registration lookup, and objections that land in the Fund's dispute register."""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta

import test_api  # noqa: F401  (sets RIE_DATABASE_URL + imports the app first)
from fastapi.testclient import TestClient
from sqlalchemy import select

from server import jws, models
from server.db import SessionLocal
from server.main import app
from server.pseudonymise import token

ops = TestClient(app)                                    # the Fund's operators (session cookie)
provider = TestClient(app)                               # a provider system (JWS only, no session)
SECRET = "rie-rails-dev-secret"
RAW_ID = "8001015009087"                                 # a made-up 13-digit identity number


def _login(user):
    assert ops.post("/api/auth/login", json={"username": user, "password": user}).status_code == 200


def _sig(obj, exp=None, jti=True):
    header = {"alg": "HS256", "exp": exp or int(time.time()) + 300}
    if jti:
        header["jti"] = jti if isinstance(jti, str) else str(uuid.uuid4())
    return {"X-JWS-Signature": jws.sign_detached(header, obj, SECRET)}


def _submit(cid, party, cas, ctype="SUPPLIER", amount=500.0, code="0190", provider_id="PR_LOOK", **kw):
    docs = ({"RAF2": True, "OAR": True, "INVOICES": True, "BANK": True} if ctype == "SUPPLIER"
            else {"RAF1": True, "OAR": True, "ID": True, "BANK": True})
    _login("handler")
    r = ops.post("/api/claims", json={
        "claim_id": cid, "claim_type": ctype, "party_token": party, "case_number_raw": cas,
        "accident_date": "2026-02-01", "lodged_on": "2026-03-01", "today": "2026-07-05",
        "payee_verified": True, "documents": docs,
        "lines": [{"kind": "TARIFF", "code": code, "qty": 1, "amount": amount,
                   "service_date": "2026-03-01", "provider_id": provider_id, "dx": "S72"}], **kw})
    assert r.status_code == 200, r.text
    return r.json()


def _status(cid, **headers):
    return provider.get(f"/rails/v1/status/{cid}", headers=headers or _sig({"claimId": cid}))


def _lookup(body, signed=True):
    return provider.post("/rails/v1/registration/lookup", json=body, headers=_sig(body) if signed else {})


def _object(body, **kw):
    return provider.post("/rails/v1/objections", json=body, headers=_sig(body, **kw))


# ── claim status ─────────────────────────────────────────────────────────────
def test_claim_status_follows_the_claim_from_receipt_to_payment():
    _submit("R_LOOK_1", "P_LOOK_1", "CAS 9901/02/2026", amount=800.0)
    s = _status("R_LOOK_1").json()
    assert (s["claimId"], s["claimType"], s["stage"], s["outcome"]) == ("R_LOOK_1", "SUPPLIER", "LODGED", "REPRICED")
    assert (s["billed"], s["payable"]) == (800.0, 500.0)
    assert s["payment"] == {"status": "NOT_QUEUED", "amount": None, "remittances": []}
    assert s["objections"] == [] and s["receivedAt"]
    assert not {"band", "score", "reasons", "holds"} & set(s)          # the risk view stays with the Fund

    _login("handler")
    bid = ops.post("/api/payments/batches", json={}).json()["id"]
    ops.post(f"/api/payments/batches/{bid}/instructions", json={"claim_id": "R_LOOK_1", "source": "SUPPLIER"})
    assert _status("R_LOOK_1").json()["payment"] == {"status": "QUEUED", "amount": 500.0, "remittances": []}
    _login("admin")
    ops.post(f"/api/payments/batches/{bid}/approve")
    assert _status("R_LOOK_1").json()["payment"]["status"] == "APPROVED"
    _login("treasury")
    ops.post(f"/api/payments/batches/{bid}/pay")
    paid = _status("R_LOOK_1").json()["payment"]
    assert paid["status"] == "PAID" and paid["amount"] == 500.0
    assert len(paid["remittances"]) == 1 and paid["remittances"][0].startswith("ERA-")


def test_claim_status_ignores_a_cancelled_batch_and_reports_a_held_claim():
    _submit("R_LOOK_2", "P_LOOK_2", "CAS 9902/02/2026")
    _login("handler")
    bid = ops.post("/api/payments/batches", json={}).json()["id"]
    ops.post(f"/api/payments/batches/{bid}/instructions", json={"claim_id": "R_LOOK_2", "source": "SUPPLIER"})
    assert ops.post(f"/api/payments/batches/{bid}/cancel").status_code == 200
    s = _status("R_LOOK_2").json()
    assert s["outcome"] == "CLEAN_PASS" and s["payment"]["status"] == "NOT_QUEUED"

    _submit("R_LOOK_3", "P_LOOK_3", "CAS 9903/02/2026", code="7777")    # no benchmark -> held for review
    assert _status("R_LOOK_3").json()["outcome"] == "HELD"


def test_claim_status_is_not_public():
    _submit("R_LOOK_4", "P_LOOK_4", "CAS 9904/02/2026")
    assert provider.get("/rails/v1/status/R_LOOK_4").status_code == 401
    assert _status("R_LOOK_4", **_sig({"claimId": "R_LOOK_1"})).status_code == 401      # bound to its claim
    assert _status("R_LOOK_4", **_sig({"claimId": "R_LOOK_4"}, exp=int(time.time()) - 5)).status_code == 401
    assert _status("R_NOPE").status_code == 404
    _login("handler")
    assert ops.get("/rails/v1/status/R_LOOK_4").status_code == 200       # an operator session may read


# ── registration lookup ──────────────────────────────────────────────────────
def test_registration_lookup_answers_only_about_what_was_supplied():
    party = token(RAW_ID, "P")
    _submit("R_LOOK_REG", party, "CAS 9910/02/2026", ctype="PERSONAL")
    ok = _lookup({"national_id": RAW_ID, "accident_date": "2026-02-01", "case_number": "cas 9910-2-26"})
    assert ok.status_code == 200
    j = ok.json()
    assert j["registered"] is True and j["code"] == "REGISTERED" and j["claimRef"] == "R_LOOK_REG"
    assert j["checks"] == {"accidentDate": "MATCH", "caseNumber": "MATCH"}
    assert j["liability"] == "PENDING" and j["undertakingActive"] is False
    assert RAW_ID not in ok.text                             # the identity number is never echoed

    by_token = _lookup({"party_token": party}).json()        # nothing else supplied -> nothing else checked
    assert by_token["registered"] is True and by_token["checks"] == {}

    wrong_date = _lookup({"national_id": RAW_ID, "accident_date": "2026-02-02"}).json()
    assert wrong_date == {"registered": False, "code": "ACCIDENT_DATE_MISMATCH",
                          "checks": {"accidentDate": "MISMATCH"},
                          "detail": "A claim exists for this claimant, but a supplied detail does not match it."}
    wrong_case = _lookup({"national_id": RAW_ID, "accident_date": "2026-02-01",
                          "case_number": "CAS 1/01/2020"}).json()
    assert wrong_case["code"] == "CASE_NUMBER_MISMATCH" and "claimRef" not in wrong_case


def test_registration_lookup_reports_liability_and_an_active_undertaking():
    party = token("7505050050080", "P")
    _submit("R_LOOK_REG2", party, "CAS 9911/02/2026", ctype="PERSONAL")
    with SessionLocal() as db:
        db.get(models.MeritsDetermination, "R_LOOK_REG2").status = "ACCEPTED"
        db.add(models.Undertaking(claim_id="R_LOOK_REG2", origin="SETTLEMENT", status="ACTIVE", scope_dx=["S72"]))
        db.commit()
    j = _lookup({"party_token": party, "accident_date": "2026-02-01"}).json()
    assert j["liability"] == "ACCEPTED" and j["undertakingActive"] is True


def test_registration_lookup_for_an_unknown_claimant_or_a_supplier_only_one():
    _submit("R_LOOK_SUP", "P_LOOK_SUPONLY", "CAS 9912/02/2026")           # a supplier claim is not a registration
    for body in ({"national_id": "9912310000000"}, {"party_token": "P_LOOK_SUPONLY"}):
        assert _lookup(body).json() == {"registered": False, "code": "NOT_REGISTERED", "checks": {},
                                        "detail": "No claim is registered for this claimant."}


def test_registration_lookup_validates_and_requires_a_signature():
    assert _lookup({"national_id": RAW_ID}, signed=False).status_code == 401
    assert "required" in _lookup({"accident_date": "2026-02-01"}).json()["detail"]
    assert "raw national ID" in _lookup({"party_token": RAW_ID}).json()["detail"]
    assert "must be a date" in _lookup({"national_id": RAW_ID, "accident_date": "1 Feb"}).json()["detail"]
    assert "police case number" in _lookup({"national_id": RAW_ID, "case_number": "none"}).json()["detail"]


# ── objections ───────────────────────────────────────────────────────────────
def test_provider_objection_lands_in_the_dispute_register_and_can_be_polled():
    _submit("R_LOOK_OBJ", "P_LOOK_OBJ", "CAS 9920/02/2026", amount=800.0, provider_id="PR_OBJ")
    body = {"claim_id": "R_LOOK_OBJ", "provider_id": "PR_OBJ", "subject": "tariff",
            "grounds": "The code was billed at the agreed specialist rate."}
    r = _object(body)
    assert r.status_code == 200, r.text
    o = r.json()
    ref = o["objectionRef"]
    assert ref.startswith("OBJ-") and o["status"] == "LODGED" and o["subject"] == "TARIFF"
    assert o["providerId"] == "PR_OBJ" and o["late"] is False and o["outcome"] is None

    _login("handler")                                        # the Fund's operators see it in their register
    mine = [d for d in ops.get("/api/disputes", params={"claim_id": "R_LOOK_OBJ"}).json()]
    assert len(mine) == 1 and mine[0]["raised_by"] == "PROVIDER" and mine[0]["opened_by"] == "provider:PR_OBJ"
    did = mine[0]["id"]
    assert ops.post(f"/api/disputes/{did}/reconsider").status_code == 200
    assert ops.post(f"/api/disputes/{did}/uphold", json={"outcome": "repriced at the specialist rate"}).status_code == 200

    polled = provider.get(f"/rails/v1/objections/{ref}", headers=_sig({"objectionRef": ref})).json()
    assert polled["status"] == "UPHELD" and polled["outcome"] == "repriced at the specialist rate"
    assert polled["channel"] == "INTERNAL" and polled["closedAt"]
    listed = provider.get("/rails/v1/objections", params={"provider_id": "PR_OBJ"},
                          headers=_sig({"providerId": "PR_OBJ"})).json()
    assert [x["objectionRef"] for x in listed] == [ref]
    assert _status("R_LOOK_OBJ").json()["objections"][0]["objectionRef"] == ref

    again = _object({**body, "grounds": "A second attempt."})   # the first is closed, so a new one may open
    assert again.status_code == 200 and again.json()["objectionRef"] != ref
    assert _object({**body, "grounds": "And a third."}).status_code == 409      # one open per claim and subject


def test_objection_guards():
    _submit("R_LOOK_OBJ2", "P_LOOK_OBJ2", "CAS 9921/02/2026", provider_id="PR_OBJ2")
    good = {"claim_id": "R_LOOK_OBJ2", "provider_id": "PR_OBJ2", "subject": "TARIFF", "grounds": "Reason."}
    assert provider.post("/rails/v1/objections", json=good).status_code == 401              # unsigned
    assert _object(good, jti=False).status_code == 400                                     # no one-time nonce
    assert _object(good, exp=int(time.time()) - 5).status_code == 401                      # expired
    assert _object({**good, "provider_id": "PR_SOMEONE_ELSE"}).status_code == 404           # not your claim
    assert _object({**good, "claim_id": "R_NOPE"}).status_code == 404
    assert "subject must be one of" in _object({**good, "subject": "MERITS"}).json()["detail"]
    assert "grounds are required" in _object({**good, "grounds": " "}).json()["detail"]
    assert "grounds are required" in _object({**good, "grounds": "x" * 2001}).json()["detail"]
    assert "are required" in _object({**good, "claim_id": ""}).json()["detail"]

    nonce = str(uuid.uuid4())
    assert _object(good, jti=nonce).status_code == 200
    replay = _object(good, jti=nonce)
    assert replay.status_code == 409 and "replay" in replay.json()["detail"]


def test_objection_reads_are_scoped_to_provider_objections():
    _submit("R_LOOK_OBJ3", "P_LOOK_OBJ3", "CAS 9922/02/2026", provider_id="PR_OBJ3")
    _login("handler")                                        # a claimant's dispute is not a provider objection
    did = ops.post("/api/disputes", json={"claim_id": "R_LOOK_OBJ3", "subject": "QUANTUM",
                                          "raised_by": "CLAIMANT", "grounds": "x"}).json()["id"]
    for ref in (f"OBJ-{did}", "OBJ-999999", "OBJ-abc", "nonsense"):
        assert provider.get(f"/rails/v1/objections/{ref}",
                            headers=_sig({"objectionRef": ref})).status_code == 404, ref
    assert provider.get(f"/rails/v1/objections/OBJ-{did}").status_code == 401
    assert provider.get("/rails/v1/objections", params={"provider_id": "PR_OBJ3"}).status_code == 401
    assert provider.get("/rails/v1/objections", params={"provider_id": "PR_OBJ3"},
                        headers=_sig({"providerId": "PR_OBJ3"})).json() == []


def test_a_late_objection_is_recorded_and_flagged_not_refused():
    _submit("R_LOOK_OBJ4", "P_LOOK_OBJ4", "CAS 9923/02/2026", provider_id="PR_OBJ4")
    with SessionLocal() as db:                               # the determination is 200 days old
        det = db.scalar(select(models.Determination).where(models.Determination.claim_id == "R_LOOK_OBJ4"))
        det.created_at = datetime.now() - timedelta(days=200)
        db.commit()
    r = _object({"claim_id": "R_LOOK_OBJ4", "provider_id": "PR_OBJ4", "subject": "REPUDIATION",
                 "grounds": "Lodged after the window."})
    assert r.status_code == 200 and r.json()["late"] is True and r.json()["status"] == "LODGED"
