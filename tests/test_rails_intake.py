"""Switch message intake, batch submission and the conformance kit (port of CIE's provider-intake
standard). The kit's runner is exercised here against the real application."""
from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path

import pytest
import test_api  # noqa: F401  (sets RIE_DATABASE_URL + imports the app first)
from fastapi.testclient import TestClient

from server import jws, models, switch_intake
from server.db import SessionLocal
from server.main import app

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "conformance"))
import refclient  # noqa: E402
import runner  # noqa: E402

ops = TestClient(app)
net = TestClient(app)
SECRET = "rie-rails-dev-secret"
RAW_ID = "8202025009081"


def _login(user="admin"):
    assert ops.post("/api/auth/login", json={"username": user, "password": user}).status_code == 200


def _register(party_id, providers, kind="PROVIDER"):
    key = jws.generate_key()
    _login()
    r = ops.post("/api/admin/rails-parties", json={"party_id": party_id, "name": party_id, "kind": kind,
                                                   "providers": providers, "public_jwk": jws.public_jwk(key)})
    assert r.status_code == 200, r.text
    return key


def _legacy(body, jti=True, exp=300):
    header = {"alg": "HS256", "exp": int(time.time()) + exp}
    if jti:
        header["jti"] = jti if isinstance(jti, str) else str(uuid.uuid4())
    return jws.sign_detached(header, body, SECRET)


def _es(key, kid, body, jti=None):
    return jws.sign_detached({"alg": "ES256", "kid": kid, "exp": int(time.time()) + 300,
                              "jti": jti or str(uuid.uuid4())}, body, key)


def _send(path, body, signature=None, idem="__new__"):
    headers = {"X-JWS-Signature": signature if signature is not None else _legacy(body)}
    if idem:
        headers["Idempotency-Key"] = str(uuid.uuid4()) if idem == "__new__" else idem
    return net.post(path, json=body, headers=headers)


def _claim(cid, provider="PR_IN", amount=500.0):
    return {"claim_id": cid, "claim_type": "SUPPLIER", "party_token": f"P_{cid}",
            "accident_date": "2026-02-01", "lodged_on": "2026-03-01", "case_number_raw": "CAS 8900/02/2026",
            "documents": {"RAF2": True, "OAR": True, "INVOICES": True, "BANK": True},
            "lines": [{"kind": "TARIFF", "code": "0190", "qty": 1, "amount": amount,
                       "service_date": "2026-03-01", "provider_id": provider, "dx": "S72"}]}


def _bhf(claim_nbr="BHF-1", provider="PR_BHF", items=None, header_extra="", pos="11", patient=None,
         service="20260302", accident="<AccidentDate>20260201</AccidentDate>"):
    items = items if items is not None else (
        "<Item><Procedure><Tariff>0190</Tariff><Quantity>1</Quantity></Procedure>"
        "<ItemFinancials><Total>800.00</Total></ItemFinancials></Item>")
    patient = patient if patient is not None else f"<Patient><IdNumber>{RAW_ID}</IdNumber></Patient>"
    return (f"<Claims><Document><ClaimHeader><Header><Vendor>KIT</Vendor><PlaceOfService>{pos}</PlaceOfService>"
            f"<Discipline>GP</Discipline></Header><BhfNumber><Treating>{provider}</Treating></BhfNumber>"
            f"<ClaimNbr>{claim_nbr}</ClaimNbr><Date><Service>{service}</Service><Created>20260305</Created></Date>"
            f"{patient}<ClaimDiagnosis><Code>S72.3</Code></ClaimDiagnosis>{accident}{header_extra}"
            f"</ClaimHeader>{items}</Document></Claims>")


# ── switch messages: the mapping ─────────────────────────────────────────────
def test_bhf_message_maps_onto_a_rails_claim():
    items = ("<Item><Procedure><Tariff>0190</Tariff><Quantity>2</Quantity></Procedure>"
             "<ItemFinancials><Total>1000.50</Total></ItemFinancials></Item>"
             "<Item><LineType>NAPPI</LineType><ServiceDate>2026-03-04</ServiceDate>"
             "<Procedure><Nappi>700101</Nappi></Procedure><ItemFinancials><Total>114.92</Total></ItemFinancials></Item>"
             "<Item><LineType>MEDICINE</LineType><Procedure><Tariff>888</Tariff></Procedure>"
             "<ItemFinancials><Total>90</Total></ItemFinancials></Item>"
             "<Item><Note>no procedure, skipped</Note></Item>")
    c = switch_intake.parse_bhf_xml(_bhf(items=items, pos="21", header_extra="<CaseNumber>CAS 12/02/2026</CaseNumber>"))
    assert (c["claim_id"], c["claim_type"], c["national_id"]) == ("BHF-1", "SUPPLIER", RAW_ID)
    assert (c["accident_date"], c["lodged_on"], c["case_number_raw"]) == ("2026-02-01", "2026-03-05", "CAS 12/02/2026")
    assert c["facility"] is True and c["documents"] == {"INVOICES": True}       # hospital place of service
    assert c["lines"] == [
        {"kind": "TARIFF", "code": "0190", "qty": 2.0, "amount": 1000.5, "service_date": "2026-03-02",
         "provider_id": "PR_BHF", "dx": "S72.3", "discipline": "GP"},
        {"kind": "NAPPI", "code": "700101", "qty": 1.0, "amount": 114.92, "service_date": "2026-03-04",
         "provider_id": "PR_BHF", "dx": "S72.3", "discipline": "GP"},
        {"kind": "NAPPI", "code": "888", "qty": 1.0, "amount": 90.0, "service_date": "2026-03-02",
         "provider_id": "PR_BHF", "dx": "S72.3", "discipline": "GP"}]

    bare = switch_intake.parse_bhf_xml(
        "<Claims><Document><ClaimHeader><BhfNumber><Supplier>SUP1</Supplier></BhfNumber>"
        "<Account><AccountNbr>ACC-9</AccountNbr></Account><Date><Service>2026-03-02</Service></Date>"
        "<Member><MemberNumber>M-77</MemberNumber></Member><AccidentDate>2026-02-01</AccidentDate></ClaimHeader>"
        "<Item><Procedure><Tariff>0190</Tariff></Procedure><ItemFinancials><Total>5</Total></ItemFinancials></Item>"
        "</Document></Claims>")
    assert (bare["claim_id"], bare["national_id"], bare["lines"][0]["provider_id"]) == ("ACC-9", "M-77", "SUP1")
    assert bare["facility"] is False and "case_number_raw" not in bare and bare["lines"][0]["dx"] == ""
    assert bare["lodged_on"] == __import__("datetime").date.today().isoformat()    # no <Created>: the Fund's date


def test_bhf_message_errors_name_what_is_wrong():
    def why(xml):
        with pytest.raises(switch_intake.SwitchError) as e:
            switch_intake.parse_bhf_xml(xml)
        assert e.value.status == 422
        return e.value.detail

    assert "must be an XML document" in why(None)
    assert "must be an XML document" in why("  ")
    assert "must be an XML document" in why("<a>" + "x" * switch_intake.MAX_MESSAGE + "</a>")
    assert "DOCTYPE or ENTITY" in why('<!DOCTYPE lolz [<!ENTITY lol "lol">]><Claims/>')
    assert "malformed XML" in why("<Claims><Document>")
    assert "no <Document>/<ClaimHeader>" in why("<Claims/>")
    assert "no <Document>/<ClaimHeader>" in why("<Claims><Document/></Claims>")
    assert "no practice number" in why(_bhf(provider=""))
    assert "no claim reference" in why(_bhf(claim_nbr=""))
    assert "no patient identity" in why(_bhf(patient=""))
    assert "no service date" in why(_bhf(service=""))
    assert "is not a date" in why(_bhf(service="20261340"))
    assert "no <AccidentDate>" in why(_bhf(accident=""))
    assert "no billable" in why(_bhf(items=""))
    assert "no <Tariff> or <Nappi>" in why(_bhf(items="<Item><Procedure/></Item>"))
    assert "<ItemFinancials>/<Total> is missing or not a number" in why(
        _bhf(items="<Item><Procedure><Tariff>1</Tariff></Procedure></Item>"))
    assert "<Quantity> is missing or not a number" in why(
        _bhf(items="<Item><Procedure><Tariff>1</Tariff><Quantity>two</Quantity></Procedure>"
                   "<ItemFinancials><Total>5</Total></ItemFinancials></Item>"))


# ── switch messages: the route ───────────────────────────────────────────────
def test_switch_message_is_scored_like_any_claim_and_the_identity_is_tokenised():
    body, key = {"format": "BHF_XML", "message": _bhf("BHF-R1")}, str(uuid.uuid4())
    r = _send("/rails/v1/claims/switch", body, idem=key)
    assert r.status_code == 200, r.text
    v = r.json()["verdict"]
    assert (v["claimId"], v["billed"], v["repricedOff"]) == ("BHF-R1", 800.0, 300.0)       # 0190 repriced to R500
    assert "held_for_validation" in v["holds"]                # a message carries no document checklist
    with SessionLocal() as db:
        claim = db.get(models.ClaimRecord, "BHF-R1")
        assert claim.party_token.startswith("P_") and RAW_ID not in str(claim.raw)
    assert _send("/rails/v1/claims/switch", body, idem=key).json()["idempotentReplay"] is True
    assert _send("/rails/v1/claims/switch", {**body, "message": _bhf("BHF-R1b")}, idem=key).status_code == 409


def test_switch_message_guards_and_scope():
    body = {"format": "BHF_XML", "message": _bhf("BHF-G1", provider="PR_BHF_G")}
    assert _send("/rails/v1/claims/switch", body, idem=None).status_code == 400            # no Idempotency-Key
    assert _send("/rails/v1/claims/switch", body, signature="").status_code == 401
    assert _send("/rails/v1/claims/switch", body, signature=_legacy(body, jti=False)).status_code == 400
    bad = {"format": "EDIFACT", "message": "UNH"}
    assert "format must be one of" in _send("/rails/v1/claims/switch", bad).json()["detail"]
    broken = {"format": "BHF_XML", "message": "<Claims/>"}
    assert _send("/rails/v1/claims/switch", broken).status_code == 422
    key = _register("KEY-BHF-G", ["PR_SOMEONE"])
    scoped = _send("/rails/v1/claims/switch", body, signature=_es(key, "KEY-BHF-G", body))
    assert scoped.status_code == 403 and "PR_BHF_G" in scoped.json()["detail"]


# ── batches ──────────────────────────────────────────────────────────────────
def test_batch_is_answered_claim_by_claim():
    key = _register("KEY-BATCH", ["PR_BATCH"])
    good, repriced = _claim("R_BAT_1", "PR_BATCH"), _claim("R_BAT_2", "PR_BATCH", amount=800.0)
    invalid = {**_claim("R_BAT_3", "PR_BATCH"), "claim_type": "NOPE"}
    foreign = _claim("R_BAT_4", "PR_SOMEONE_ELSE")
    body = {"claims": [good, repriced, invalid, foreign, "not a claim", {"lines": []}]}
    idem = str(uuid.uuid4())
    r = _send("/rails/v1/batches", body, signature=_es(key, "KEY-BATCH", body), idem=idem)
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["claims"] == 6 and b["idempotentReplay"] is False
    assert b["summary"] == {"CLEAN_PASS": 1, "REPRICED": 1, "REJECTED": 4, "deduplicated": 0}
    one, two, three, four, five, six = b["results"]
    assert (one["status"], one["verdict"]["outcome"], one["deduplicated"]) == (200, "CLEAN_PASS", False)
    assert two["verdict"]["repricedOff"] == 300.0 and jws.peek_header(two["receipt"]["signature"])["alg"] == "ES256"
    assert three["status"] == 422 and "invalid claim" in three["error"]
    assert four["status"] == 403 and "PR_SOMEONE_ELSE" in four["error"]
    assert five == {"index": 4, "claimId": None, "status": 422, "error": "each claim must be an object"}
    assert six["status"] == 422 and six["claimId"] is None
    with SessionLocal() as db:                                # one bad claim did not fail the file
        assert db.get(models.ClaimRecord, "R_BAT_1") is not None and db.get(models.ClaimRecord, "R_BAT_4") is None

    # a resend of the same file returns the stored batch; a new file dedupes what was already done
    again = _send("/rails/v1/batches", body, signature=_es(key, "KEY-BATCH", body), idem=idem).json()
    assert again["batchId"] == b["batchId"] and again["idempotentReplay"] is True
    nxt = {"claims": [good, _claim("R_BAT_5", "PR_BATCH")]}
    n = _send("/rails/v1/batches", nxt, signature=_es(key, "KEY-BATCH", nxt)).json()
    assert n["results"][0]["deduplicated"] is True and n["results"][0]["submissionId"] == one["submissionId"]
    assert n["results"][1]["deduplicated"] is False and n["summary"]["deduplicated"] == 1

    # read-back: the sender and an operator, nobody else
    bid = b["batchId"]
    sig = {"X-JWS-Signature": _es(key, "KEY-BATCH", {"batchId": bid})}
    assert net.get(f"/rails/v1/batches/{bid}", headers=sig).json()["results"] == b["results"]
    other = _register("KEY-BATCH-2", ["PR_BATCH"])
    assert net.get(f"/rails/v1/batches/{bid}",
                   headers={"X-JWS-Signature": _es(other, "KEY-BATCH-2", {"batchId": bid})}).status_code == 404
    assert net.get(f"/rails/v1/batches/{bid}").status_code == 401
    assert net.get("/rails/v1/batches/nope", headers={"X-JWS-Signature": _es(key, "KEY-BATCH", {"batchId": "nope"})}).status_code == 404
    _login("handler")
    assert ops.get(f"/rails/v1/batches/{bid}").status_code == 200
    stolen = _send("/rails/v1/batches", body, signature=_es(other, "KEY-BATCH-2", body), idem=idem)
    assert stolen.status_code == 409 and "another party" in stolen.json()["detail"]


def test_batch_guards():
    body = {"claims": [_claim("R_BAT_G1")]}
    assert _send("/rails/v1/batches", body, idem=None).status_code == 400
    assert _send("/rails/v1/batches", body, signature="x").status_code == 401
    for claims in (None, [], "x", [{}] * 101):
        bad = {"claims": claims}
        assert "claims must be a list" in _send("/rails/v1/batches", bad).json()["detail"]
    idem, nonce = str(uuid.uuid4()), str(uuid.uuid4())
    assert _send("/rails/v1/batches", body, signature=_legacy(body, jti=nonce), idem=idem).status_code == 200
    changed = {"claims": [_claim("R_BAT_G2")]}
    assert _send("/rails/v1/batches", changed, idem=idem).status_code == 409                    # same key, other file
    replay = _send("/rails/v1/batches", body, signature=_legacy(body, jti=nonce))
    assert replay.status_code == 409 and "replay" in replay.json()["detail"]


# ── the conformance kit ──────────────────────────────────────────────────────
def _transport(method, path, body, headers):
    r = net.request(method, path, json=body, headers=headers)
    try:
        return r.status_code, r.json()
    except ValueError:
        return r.status_code, r.text


def test_reference_client_signatures_are_the_servers_signatures():
    key = refclient.generate_key()
    token = refclient.sign(key, "kid-1", {"b": 2, "a": 1})
    assert jws.verify_es256(token, {"a": 1, "b": 2}, refclient.public_jwk(key))["kid"] == "kid-1"
    server_token = jws.sign_detached({"alg": "ES256", "kid": "f"}, {"a": 1}, key)
    assert refclient.verify(server_token, {"a": 1}, refclient.public_jwk(key)) is True
    assert refclient.verify(server_token, {"a": 2}, refclient.public_jwk(key)) is False
    assert refclient.verify("nonsense", {}, refclient.public_jwk(key)) is False
    assert refclient.verify(jws.sign_detached({"alg": "HS256"}, {}, "s"), {}, refclient.public_jwk(key)) is False
    assert refclient.thumbprint(refclient.public_jwk(key)) == jws.thumbprint(jws.public_jwk(key))
    assert jws.clean_public_jwk(refclient.public_jwk(key)) == refclient.public_jwk(key)


def test_keygen_writes_a_private_key_and_prints_only_the_public_half(tmp_path, capsys):
    path = tmp_path / "k.pem"
    assert refclient.main(["keygen", str(path)]) == 0
    printed = capsys.readouterr().out
    key = refclient.load_key(str(path))
    assert refclient.public_jwk(key)["x"] in printed and "PRIVATE KEY" not in printed and '"d"' not in printed
    assert refclient.main([]) == 2 and refclient.main(["submit"]) == 2


def test_a_registered_party_passes_every_conformance_check():
    key = _register("KEY-CONF", ["PR_CONF"])
    client = refclient.Client(_transport, "KEY-CONF", key)
    lines: list[str] = []
    results = runner.run(client, "PR_CONF", out=lines.append)
    failed = [(n, d) for n, ok, d in results if not ok]
    assert failed == [] and len(results) == 17
    assert any("PASS  a BHF XML switch message" in x for x in lines)


def test_the_runner_reports_failures_for_a_party_that_is_not_allowed():
    key = _register("KEY-CONF-BAD", ["PR_CONF_OTHER"])          # registered, but not for this provider
    results = runner.run(refclient.Client(_transport, "KEY-CONF-BAD", key), "PR_CONF", out=lambda _x: None)
    by_name = {n: ok for n, ok, _d in results}
    assert by_name["the Fund publishes its signing key"] is True
    assert by_name["a signed claim is accepted and answered with a verdict"] is False
    assert sum(1 for ok in by_name.values() if not ok) >= 5
    stranger = refclient.Client(_transport, "KEY-CONF-BAD", refclient.generate_key())
    assert stranger.receipt_is_genuine({"signature": "bad"}) is False
