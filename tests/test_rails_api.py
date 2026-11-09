"""Provider->fund rails — the signed Core Rails round-trip + idempotency/replay/auth guards."""
from __future__ import annotations

import time
import uuid

import test_api  # noqa: F401  (sets RIE_DATABASE_URL + imports the app first)
from fastapi.testclient import TestClient
from server import jws
from server.main import app

client = TestClient(app)
SECRET = "rie-rails-dev-secret"                          # matches config.RAILS_SECRET default


def _claim(cid, party, cas, amount=500.0):
    return {"claim_id": cid, "claim_type": "SUPPLIER", "party_token": party,
            "accident_date": "2026-02-01", "lodged_on": "2026-03-01", "case_number_raw": cas,
            "today": "2026-07-05", "payee_verified": True,
            "documents": {"RAF2": True, "OAR": True, "INVOICES": True, "BANK": True},
            "lines": [{"kind": "TARIFF", "code": "0190", "qty": 1, "amount": amount,
                       "service_date": "2026-03-01", "provider_id": "PR_RAILS", "dx": "S72"}]}


def _sign(body, jti=None, exp=None):
    header = {"alg": "HS256", "jti": jti or str(uuid.uuid4()), "exp": exp or int(time.time()) + 300}
    return jws.sign_detached(header, body, SECRET)


def _submit(body, idem=None, jti=None, sig="__auto__"):
    signature = _sign(body, jti) if sig == "__auto__" else sig
    return client.post("/rails/v1/claims", json=body, headers={
        "Idempotency-Key": idem or str(uuid.uuid4()), "X-JWS-Signature": signature})


def test_clean_submission_signed_verdict_and_readback():
    body = _claim("R_rail1", "P_rail1", "CAS 9700/02/2026")
    r = _submit(body)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["verdict"]["outcome"] == "CLEAN_PASS"
    assert j["verdict"]["billed"] == 500.0 and j["verdict"]["payableNow"] == 500.0
    receipt = dict(j["receipt"])
    sig = receipt.pop("signature")
    assert jws.verify_detached(sig, receipt, SECRET) is not None       # fund-signed receipt verifies
    sid = j["submissionId"]
    assert client.get(f"/rails/v1/claims/{sid}").status_code == 401          # verdicts are not public
    read_sig = jws.sign_detached({"alg": "HS256", "jti": str(uuid.uuid4())}, {"submissionId": sid}, SECRET)
    assert client.get(f"/rails/v1/claims/{sid}",
                      headers={"X-JWS-Signature": read_sig}).json()["outcome"] == "CLEAN_PASS"
    # the provider asserted payee_verified; the fund dropped it -> the hold is on until the fund verifies
    assert "PAYEE_UNVERIFIED" in j["verdict"]["holds"]


def test_repriced_outcome():
    v = _submit(_claim("R_rail2", "P_rail2", "CAS 9701/02/2026", amount=800.0)).json()["verdict"]
    assert v["outcome"] == "REPRICED" and v["repricedOff"] == 300.0 and v["payableNow"] == 500.0


def test_idempotent_retry_returns_same_verdict():
    body = _claim("R_rail3", "P_rail3", "CAS 9702/02/2026")
    idem = str(uuid.uuid4())
    sid = _submit(body, idem=idem).json()["submissionId"]
    again = _submit(body, idem=idem, jti=str(uuid.uuid4())).json()     # same key, same body
    assert again["submissionId"] == sid and again.get("idempotentReplay") is True


def test_idempotency_key_reuse_different_body_409():
    idem = str(uuid.uuid4())
    _submit(_claim("R_rail4", "P_rail4", "CAS 9703/02/2026"), idem=idem)
    assert _submit(_claim("R_rail4b", "P_rail4b", "CAS 9704/02/2026"), idem=idem).status_code == 409


def test_replay_jti_rejected():
    jti = str(uuid.uuid4())
    _submit(_claim("R_rail5", "P_rail5", "CAS 9705/02/2026"), jti=jti)
    assert _submit(_claim("R_rail6", "P_rail6", "CAS 9706/02/2026"), jti=jti).status_code == 409


def test_bad_and_wrong_key_signature_401():
    body = _claim("R_rail7", "P_rail7", "CAS 9707/02/2026")
    assert _submit(body, sig="tampered..xxxx").status_code == 401
    wrong = jws.sign_detached({"alg": "HS256", "jti": "x", "exp": int(time.time()) + 300},
                              body, "WRONG-SECRET")
    assert _submit(body, sig=wrong).status_code == 401


def test_expired_signature_401():
    body = _claim("R_rail8", "P_rail8", "CAS 9708/02/2026")
    assert _submit(body, sig=_sign(body, exp=int(time.time()) - 10)).status_code == 401


def test_missing_idempotency_key_400():
    body = _claim("R_rail9", "P_rail9", "CAS 9709/02/2026")
    r = client.post("/rails/v1/claims", json=body, headers={"X-JWS-Signature": _sign(body)})
    assert r.status_code == 400
