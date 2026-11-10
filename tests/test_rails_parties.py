"""Per-party signing keys on the rails channel (port of CIE's asymmetric signing and switch
registry): a party signs with its own ES256 key, the Fund verifies with the registered public key,
and every route is scoped to the providers that party may act for."""
from __future__ import annotations

import time
import uuid

import pytest
import test_api  # noqa: F401  (sets RIE_DATABASE_URL + imports the app first)
from fastapi.testclient import TestClient
from sqlalchemy import select

from server import config, jws, models, rails_auth
from server.db import SessionLocal
from server.main import app

ops = TestClient(app)                                    # the Fund's operators (session cookie)
net = TestClient(app)                                    # the open network (no session)
SECRET = "rie-rails-dev-secret"


def _login(user="admin"):
    assert ops.post("/api/auth/login", json={"username": user, "password": user}).status_code == 200


def _register(party_id, providers, kind="PROVIDER", key=None):
    key = key or jws.generate_key()
    _login()
    r = ops.post("/api/admin/rails-parties", json={
        "party_id": party_id, "name": party_id, "kind": kind, "providers": providers,
        "public_jwk": jws.public_jwk(key)})
    assert r.status_code == 200, r.text
    return key


def _sig(key, kid, obj, exp=300, jti=True, **extra):
    header = {"alg": "ES256", "kid": kid, **extra}
    if exp is not None:
        header["exp"] = int(time.time()) + exp
    if jti:
        header["jti"] = jti if isinstance(jti, str) else str(uuid.uuid4())
    return {"X-JWS-Signature": jws.sign_detached(header, obj, key)}


def _claim(cid, provider, party=None, amount=500.0):
    return {"claim_id": cid, "claim_type": "SUPPLIER", "party_token": party or f"P_{cid}",
            "accident_date": "2026-02-01", "lodged_on": "2026-03-01", "case_number_raw": "CAS 8800/02/2026",
            "documents": {"RAF2": True, "OAR": True, "INVOICES": True, "BANK": True},
            "lines": [{"kind": "TARIFF", "code": "0190", "qty": 1, "amount": amount,
                       "service_date": "2026-03-01", "provider_id": provider, "dx": "S72"}]}


def _post(path, body, key, kid, idem=None, **kw):
    return net.post(path, json=body, headers={"Idempotency-Key": idem or str(uuid.uuid4()),
                                              **_sig(key, kid, body, **kw)})


def _get(path, subject, key, kid, **params):
    return net.get(path, params=params or None, headers=_sig(key, kid, subject))


@pytest.fixture(scope="module")
def parties():
    """Two provider systems and a switch, each with its own key."""
    return {"A": _register("KEY-PR-A", ["PR_KEY_A"]), "B": _register("KEY-PR-B", ["PR_KEY_B"]),
            "S": _register("KEY-SWITCH", ["*"], kind="SWITCH")}


# ── ES256 itself ─────────────────────────────────────────────────────────────
def test_es256_sign_and_verify():
    key, other = jws.generate_key(), jws.generate_key()
    jwk = jws.public_jwk(key)
    token = jws.sign_detached({"alg": "ES256", "kid": "k"}, {"a": 1, "b": 2}, key)
    assert jws.verify_es256(token, {"b": 2, "a": 1}, jwk) == {"alg": "ES256", "kid": "k"}   # canonical: order-free
    assert jws.verify_es256(token, {"a": 2, "b": 2}, jwk) is None                           # body changed
    assert jws.verify_es256(token, {"a": 1, "b": 2}, jws.public_jwk(other)) is None         # another key
    assert jws.verify_es256("garbage", {}, jwk) is None and jws.peek_header("a.b.c") is None
    assert jws.verify_es256(jws.sign_detached({"alg": "HS256"}, {}, "s"), {}, jwk) is None  # alg is pinned
    head = token.split(".")[0]
    assert jws.verify_es256(f"{head}..AAAA", {"a": 1, "b": 2}, jwk) is None                 # not 64 bytes
    assert jws.verify_es256(token, {"a": 1, "b": 2}, {"x": "!", "y": "!"}) is None          # unusable key
    assert jws.peek_header(token)["kid"] == "k" and jws.peek_header(None) is None

    reloaded = jws.load_private_key(jws.private_pem(key))                                   # PEM round trip
    assert jws.public_jwk(reloaded, "kid-1") == {**jwk, "kid": "kid-1"}
    assert jws.thumbprint(jwk) == jws.thumbprint(jws.public_jwk(reloaded)) != jws.thumbprint(jws.public_jwk(other))


def test_only_a_p256_public_key_can_be_registered():
    key = jws.generate_key()
    jwk = jws.public_jwk(key)
    assert jws.clean_public_jwk({**jwk, "kid": "x", "extra": 1}) == {k: jwk[k] for k in ("kty", "crv", "x", "y")}
    private = {**jwk, "d": "c2VjcmV0"}
    for bad, why in ((private, "PRIVATE key"), ("text", "EC P-256"), ({**jwk, "crv": "P-384"}, "EC P-256"),
                     ({**jwk, "kty": "RSA"}, "EC P-256"), ({**jwk, "x": "AAAA"}, "point on P-256"),
                     ({"kty": "EC", "crv": "P-256"}, "point on P-256"),
                     ({**jwk, "y": jwk["x"]}, "point on P-256")):
        with pytest.raises(ValueError, match=why):
            jws.clean_public_jwk(bad)


# ── the register ─────────────────────────────────────────────────────────────
def test_register_is_admin_only_and_validated():
    jwk = jws.public_jwk(jws.generate_key())
    _login("handler")
    assert ops.get("/api/admin/rails-parties").status_code == 403
    assert ops.post("/api/admin/rails-parties", json={}).status_code == 403
    _login()

    def bad(**change):
        body = {"party_id": "KEY-VALID", "name": "n", "kind": "PROVIDER", "providers": ["PR1"],
                "public_jwk": jwk, **change}
        r = ops.post("/api/admin/rails-parties", json=body)
        assert r.status_code == 400, r.text
        return r.json()["detail"]

    assert "party id must be" in bad(party_id="x")
    assert "kind must be one of" in bad(kind="BROKER")
    assert "providers must be a list" in bad(providers=[])
    assert "providers must be a list" in bad(providers="PR1")
    assert "1 to 64 characters" in bad(providers=["x" * 65])
    assert "SWITCH only" in bad(providers=["*"])
    assert "SWITCH only" in bad(kind="SWITCH", providers=["*", "PR1"])
    assert "must be a JWK" in bad(public_jwk="not json")
    assert "PRIVATE key" in bad(public_jwk={**jwk, "d": "c2VjcmV0"})
    assert all(p["party_id"] != "KEY-VALID" for p in ops.get("/api/admin/rails-parties").json())


def test_register_update_suspend_and_rotate(parties):
    _login()
    import json
    key = jws.generate_key()
    made = ops.post("/api/admin/rails-parties", json={
        "party_id": "KEY-ADMIN", "name": "  Admin test  ", "kind": "PROVIDER",
        "providers": ["PR_Z", "PR_Y", "PR_Y"], "public_jwk": json.dumps(jws.public_jwk(key))}).json()
    assert made["providers"] == ["PR_Y", "PR_Z"] and made["name"] == "Admin test" and made["status"] == "ACTIVE"
    assert made["key_thumbprint"] == jws.thumbprint(jws.public_jwk(key)) and "public_jwk" not in made
    dup = ops.post("/api/admin/rails-parties", json={"party_id": "KEY-ADMIN", "kind": "PROVIDER",
                                                     "providers": ["P"], "public_jwk": jws.public_jwk(key)})
    assert dup.status_code == 400 and "already registered" in dup.json()["detail"]

    assert ops.post("/api/admin/rails-parties/KEY-ADMIN/providers", json={"providers": ["PR_Q"]}).json()["providers"] == ["PR_Q"]
    assert ops.post("/api/admin/rails-parties/KEY-ADMIN/status", json={"status": "SUSPENDED"}).json()["status"] == "SUSPENDED"
    assert "status must be" in ops.post("/api/admin/rails-parties/KEY-ADMIN/status", json={"status": "GONE"}).json()["detail"]
    new = jws.generate_key()
    rotated = ops.post("/api/admin/rails-parties/KEY-ADMIN/key", json={"public_jwk": jws.public_jwk(new)}).json()
    assert rotated["key_thumbprint"] == jws.thumbprint(jws.public_jwk(new)) != made["key_thumbprint"]
    for path, body in (("status", {"status": "ACTIVE"}), ("providers", {"providers": ["P"]}),
                       ("key", {"public_jwk": jws.public_jwk(new)})):
        r = ops.post(f"/api/admin/rails-parties/KEY-NOPE/{path}", json=body)
        assert r.status_code == 400 and "no such party" in r.json()["detail"]
    with SessionLocal() as db:
        actions = [a.action for a in db.scalars(select(models.AdminAudit)
                                                .where(models.AdminAudit.target == "KEY-ADMIN"))]
    assert actions == ["rails_party.register", "rails_party.providers", "rails_party.status", "rails_party.rotate_key"]
    assert {"KEY-PR-A", "KEY-PR-B", "KEY-SWITCH", "KEY-ADMIN"} <= {p["party_id"] for p in ops.get("/api/admin/rails-parties").json()}


# ── signing a claim ──────────────────────────────────────────────────────────
def test_party_signs_with_its_key_and_the_fund_signs_back(parties):
    r = _post("/rails/v1/claims", _claim("R_KEY_1", "PR_KEY_A"), parties["A"], "KEY-PR-A")
    assert r.status_code == 200, r.text
    receipt = dict(r.json()["receipt"])
    token = receipt.pop("signature")
    header = jws.peek_header(token)
    assert header["alg"] == "ES256" and header["iss"] == "RAF-RIE"
    published = {k["kid"]: k for k in net.get("/rails/v1/.well-known/jwks.json").json()["keys"]}   # public, unsigned
    assert jws.verify_es256(token, receipt, published[header["kid"]]) is not None
    assert jws.verify_es256(token, {**receipt, "payableNow": 1.0}, published[header["kid"]]) is None
    with SessionLocal() as db:
        assert db.scalar(select(models.RailsSubmission.party_id)
                         .where(models.RailsSubmission.claim_id == "R_KEY_1")) == "KEY-PR-A"


def test_a_key_acts_only_for_its_own_providers(parties):
    theirs = _post("/rails/v1/claims", _claim("R_KEY_2", "PR_KEY_B"), parties["A"], "KEY-PR-A")
    assert theirs.status_code == 403 and "may not act for provider PR_KEY_B" in theirs.json()["detail"]
    mixed = _claim("R_KEY_3", "PR_KEY_A")
    mixed["lines"].append({**mixed["lines"][0], "provider_id": "PR_KEY_B", "amount": 400.0})
    assert _post("/rails/v1/claims", mixed, parties["A"], "KEY-PR-A").status_code == 403
    with SessionLocal() as db:                               # nothing was stored for the refused claims
        assert db.get(models.ClaimRecord, "R_KEY_2") is None and db.get(models.ClaimRecord, "R_KEY_3") is None
    assert _post("/rails/v1/claims", mixed, parties["S"], "KEY-SWITCH").status_code == 200   # a switch acts for any


def test_signature_must_be_the_registered_keys_and_fresh(parties):
    body = _claim("R_KEY_BAD", "PR_KEY_A")

    def refused(key, kid, **kw):
        r = _post("/rails/v1/claims", body, key, kid, **kw)
        assert r.status_code == 401, r.text
        return r.json()["detail"]

    assert "unknown or suspended" in refused(parties["A"], "KEY-NOBODY")
    assert "invalid or missing" in refused(parties["B"], "KEY-PR-A")           # B's key under A's name
    assert "exp (expiry) required" in refused(parties["A"], "KEY-PR-A", exp=None)
    assert "signature expired" in refused(parties["A"], "KEY-PR-A", exp=-5)
    assert "seconds ahead" in refused(parties["A"], "KEY-PR-A", exp=3600)
    assert _post("/rails/v1/claims", body, parties["A"], "KEY-PR-A", jti=False).status_code == 400
    assert net.post("/rails/v1/claims", json=body, headers={
        "Idempotency-Key": "k", "X-JWS-Signature": "not.a.jws"}).status_code == 401


def test_suspension_and_rotation_take_effect_at_once():
    old = _register("KEY-ROT", ["PR_KEY_ROT"])
    assert _post("/rails/v1/claims", _claim("R_KEY_ROT1", "PR_KEY_ROT"), old, "KEY-ROT").status_code == 200
    _login()
    ops.post("/api/admin/rails-parties/KEY-ROT/status", json={"status": "SUSPENDED"})
    assert _post("/rails/v1/claims", _claim("R_KEY_ROT2", "PR_KEY_ROT"), old, "KEY-ROT").status_code == 401
    ops.post("/api/admin/rails-parties/KEY-ROT/status", json={"status": "ACTIVE"})
    new = jws.generate_key()
    ops.post("/api/admin/rails-parties/KEY-ROT/key", json={"public_jwk": jws.public_jwk(new)})
    assert _post("/rails/v1/claims", _claim("R_KEY_ROT2", "PR_KEY_ROT"), old, "KEY-ROT").status_code == 401
    assert _post("/rails/v1/claims", _claim("R_KEY_ROT2", "PR_KEY_ROT"), new, "KEY-ROT").status_code == 200


def test_an_idempotency_key_belongs_to_the_party_that_used_it(parties):
    body, key = _claim("R_KEY_IDEM", "PR_KEY_A"), str(uuid.uuid4())
    assert _post("/rails/v1/claims", body, parties["A"], "KEY-PR-A", idem=key).status_code == 200
    assert _post("/rails/v1/claims", body, parties["A"], "KEY-PR-A", idem=key).json()["idempotentReplay"] is True
    stolen = _post("/rails/v1/claims", body, parties["S"], "KEY-SWITCH", idem=key)
    assert stolen.status_code == 409 and "another party" in stolen.json()["detail"]


# ── every read and write is scoped ───────────────────────────────────────────
def test_parties_see_only_their_own_providers_records(parties):
    a, b = parties["A"], parties["B"]
    # provider B's claim, paid, with an objection and a medical report of its own
    _login("handler")
    assert ops.post("/api/claims", json={**_claim("R_KEY_B1", "PR_KEY_B"), "payee_verified": True,
                                         "today": "2026-07-05"}).status_code == 200
    bid = ops.post("/api/payments/batches", json={}).json()["id"]
    ops.post(f"/api/payments/batches/{bid}/instructions", json={"claim_id": "R_KEY_B1", "source": "SUPPLIER"})
    _login("admin")
    ops.post(f"/api/payments/batches/{bid}/approve")
    _login("treasury")
    assert ops.post(f"/api/payments/batches/{bid}/pay").json()["status"] == "PAID"
    rem = _get("/rails/v1/remittances", {"providerId": "PR_KEY_B"}, b, "KEY-PR-B", provider_id="PR_KEY_B").json()[0]["ref"]
    obj_body = {"claim_id": "R_KEY_B1", "provider_id": "PR_KEY_B", "subject": "TARIFF", "grounds": "g"}
    obj = _post("/rails/v1/objections", obj_body, b, "KEY-PR-B").json()["objectionRef"]
    mr_body = {"form_code": "RAF1-MR", "provider_id": "PR_KEY_B", "claim_ref": "R_KEY_B1",
               "sections": [{"title": "t", "fields": [{"label": "l", "value": "v"}]}]}
    mr = _post("/rails/v1/medical-reports", mr_body, b, "KEY-PR-B").json()["ref"]
    sub = _post("/rails/v1/claims", _claim("R_KEY_B2", "PR_KEY_B"), b, "KEY-PR-B").json()["submissionId"]

    by_ref = [(f"/rails/v1/claims/{sub}", {"submissionId": sub}), ("/rails/v1/status/R_KEY_B1", {"claimId": "R_KEY_B1"}),
              (f"/rails/v1/remittances/{rem}", {"remittanceRef": rem}), (f"/rails/v1/objections/{obj}", {"objectionRef": obj}),
              (f"/rails/v1/medical-reports/{mr}", {"reportRef": mr}),
              ("/rails/v1/claims/R_KEY_B1/documentation", {"claimId": "R_KEY_B1"})]
    for path, subject in by_ref:
        assert _get(path, subject, b, "KEY-PR-B").status_code == 200, path          # its own
        assert _get(path, subject, a, "KEY-PR-A").status_code == 404, path          # another's looks absent
        assert _get(path, subject, parties["S"], "KEY-SWITCH").status_code == 200, path   # a switch for any
    for path in ("/rails/v1/remittances", "/rails/v1/objections", "/rails/v1/medical-reports"):
        subject = {"providerId": "PR_KEY_B"}
        assert _get(path, subject, b, "KEY-PR-B", provider_id="PR_KEY_B").status_code == 200, path
        assert _get(path, subject, a, "KEY-PR-A", provider_id="PR_KEY_B").status_code == 403, path

    ack = net.post(f"/rails/v1/remittances/{rem}/ack", headers=_sig(a, "KEY-PR-A", {"remittanceRef": rem}))
    assert ack.status_code == 404
    assert net.post(f"/rails/v1/remittances/{rem}/ack",
                    headers=_sig(b, "KEY-PR-B", {"remittanceRef": rem})).json()["status"] == "ACKNOWLEDGED"
    assert _post("/rails/v1/objections", {**obj_body, "subject": "QUANTUM"}, a, "KEY-PR-A").status_code == 403
    assert _post("/rails/v1/medical-reports", mr_body, a, "KEY-PR-A").status_code == 403

    _login("handler")                                        # an operator is not provider-scoped
    assert ops.get(f"/rails/v1/remittances/{rem}").status_code == 200
    assert ops.get("/rails/v1/status/R_KEY_B1").status_code == 200


def test_any_registered_party_may_look_up_a_registration(parties):
    body = {"party_token": "P_KEY_NOBODY", "accident_date": "2026-02-01"}
    r = net.post("/rails/v1/registration/lookup", json=body, headers=_sig(parties["A"], "KEY-PR-A", body))
    assert r.status_code == 200 and r.json()["code"] == "NOT_REGISTERED"
    assert net.post("/rails/v1/registration/lookup", json=body).status_code == 401
    forms = net.get("/rails/v1/medical-reports/forms",
                    headers=_sig(parties["A"], "KEY-PR-A", {"catalogue": "medical-report-forms"}))
    assert forms.status_code == 200 and len(forms.json()) == 2


# ── the shared secret ────────────────────────────────────────────────────────
def test_shared_secret_is_refused_once_it_is_switched_off(parties, monkeypatch):
    body = _claim("R_KEY_LEGACY", "PR_KEY_A")
    legacy = {"Idempotency-Key": str(uuid.uuid4()), "X-JWS-Signature": jws.sign_detached(
        {"alg": "HS256", "jti": str(uuid.uuid4()), "exp": int(time.time()) + 300}, body, SECRET)}
    monkeypatch.setattr(config, "RAILS_SHARED_SECRET_ENABLED", False)
    assert net.post("/rails/v1/claims", json=body, headers=legacy).status_code == 401
    assert net.get("/rails/v1/status/R_KEY_1", headers={"X-JWS-Signature": jws.sign_detached(
        {"alg": "HS256"}, {"claimId": "R_KEY_1"}, SECRET)}).status_code == 401
    assert _post("/rails/v1/claims", body, parties["A"], "KEY-PR-A").status_code == 200   # a registered key still works
    monkeypatch.setattr(config, "RAILS_SHARED_SECRET_ENABLED", True)
    legacy_ok = net.get("/rails/v1/status/R_KEY_1", headers={"X-JWS-Signature": jws.sign_detached(
        {"alg": "HS256"}, {"claimId": "R_KEY_1"}, SECRET)})
    assert legacy_ok.status_code == 200                                              # on in dev and test


def test_the_fund_key_can_be_supplied_from_configuration(monkeypatch):
    supplied = jws.generate_key()
    saved = dict(rails_auth._fund)
    try:
        rails_auth._fund.clear()
        monkeypatch.setattr(config, "RAILS_SIGNING_KEY_PEM", jws.private_pem(supplied))
        published = rails_auth.jwks()["keys"]
        assert published == [jws.public_jwk(supplied, jws.thumbprint(jws.public_jwk(supplied)))]
        caller = rails_auth.Caller("p", "PROVIDER", "ES256", frozenset({"X"}))
        token = rails_auth.sign_for(caller, {"a": 1})
        assert jws.verify_es256(token, {"a": 1}, published[0])["kid"] == published[0]["kid"]
        assert caller.may_act_for("X") and not caller.may_act_for("Y") and caller.may_act_for_any(["Y", "X"])
    finally:
        rails_auth._fund.clear()
        rails_auth._fund.update(saved)
