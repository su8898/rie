"""POPIA HMAC pseudonymisation at ingest (§2/§4/§9) — raw national IDs become stable P_* tokens
and are never persisted."""
from __future__ import annotations

import test_api  # noqa: F401  (sets RIE_DATABASE_URL + imports the app + seeds)
from fastapi.testclient import TestClient
from server import models
from server.db import SessionLocal
from server.main import app
from server.pseudonymise import PII_FIELDS, pseudonymise_ingest, token

client = TestClient(app)


def _login(user="handler"):
    assert client.post("/api/auth/login", json={"username": user, "password": user}).status_code == 200


# ── the pseudonymiser (pure) ──────────────────────────────────────────────────
def test_token_is_deterministic_and_prefixed():
    t1, t2 = token("8501015800083", "P"), token("8501015800083", "P")
    assert t1 == t2 and t1.startswith("P_") and len(t1) > 3


def test_token_varies_by_id_and_prefix():
    assert token("111", "P") != token("222", "P")       # different people
    assert token("111", "P") != token("111", "A")       # different namespaces


def test_ingest_derives_party_token_and_strips_pii():
    p = pseudonymise_ingest({"id_number": "9001010001088", "claimant_name": "Jane Doe",
                             "claim_id": "R1", "claim_type": "SUPPLIER"})
    assert p["party_token"] == token("9001010001088", "P")
    assert "id_number" not in p and "claimant_name" not in p    # raw PII dropped
    assert p["claim_id"] == "R1" and p["claim_type"] == "SUPPLIER"   # non-PII passes through


def test_ingest_preserves_a_supplied_pseudonymous_token():
    p = pseudonymise_ingest({"party_token": "P_manual", "claim_id": "R2"})
    assert p["party_token"] == "P_manual"


def test_same_person_maps_to_same_token_across_claims():
    a = pseudonymise_ingest({"id_number": "X"})["party_token"]
    b = pseudonymise_ingest({"id_number": "X", "claim_id": "other"})["party_token"]
    assert a == b                                        # stable pseudonym -> party recurrence works


def test_every_declared_pii_field_is_stripped():
    payload = {f: "secret" for f in PII_FIELDS}
    payload["claim_id"] = "R3"
    out = pseudonymise_ingest(payload)
    assert not any(f in out for f in PII_FIELDS) and out["claim_id"] == "R3"


# ── end-to-end: /api/claims must not persist the raw ID ───────────────────────
def test_claim_ingest_pseudonymises_and_never_stores_raw_id():
    _login("handler")
    raw_id = "9202025009087"
    claim = {"claim_id": "R_pii1", "claim_type": "SUPPLIER", "id_number": raw_id,
             "accident_date": "2026-02-01", "lodged_on": "2026-03-01",
             "case_number_raw": "CAS 9/02/2026", "today": "2026-07-05",
             "documents": {"RAF2": True, "OAR": True, "INVOICES": True, "BANK": True},
             "payee_verified": True,
             "lines": [{"kind": "TARIFF", "code": "0190", "qty": 1, "amount": 500.0,
                        "service_date": "2026-03-01", "provider_id": "PR1", "dx": "S72"}]}
    assert client.post("/api/claims", json=claim).status_code == 200
    with SessionLocal() as db:
        rec = db.get(models.ClaimRecord, "R_pii1")
    assert rec.party_token == token(raw_id, "P")         # stored as the derived P_* token
    assert "id_number" not in rec.raw                    # raw national ID never persisted
    assert rec.raw.get("party_token") == token(raw_id, "P")
