"""Regression tests for the twelve High findings of the 2026-11-09 review, as threaded through the
server (the engine-level behaviour is pinned in tests/scenarios.py + the per-module unit tests).

H1 calendar-year prescription · H2 cross-claim pay-once ledger + one claim per claimant per
accident · H3 one code identity · H5 ADVISORY never routes · H6 uncovered codes are held for
review and flagged · H7 collision-free accident ids, WORKLIST never auto-joins · H8 Grounded
gates ignore a stored SHADOW override · H9 dashboard/list count the latest determination only ·
H11 PII stripped at every depth · H12 exact money."""
from __future__ import annotations

from datetime import date

import test_api  # noqa: F401  (sets RIE_DATABASE_URL + imports the app first)
from fastapi.testclient import TestClient

from server import models
from server.db import SessionLocal
from server.main import app
from server.pseudonymise import pseudonymise_ingest, token

client = TestClient(app)
LINE = {"kind": "TARIFF", "code": "0190", "qty": 1, "amount": 500.0,
        "service_date": "2026-03-01", "provider_id": "PR_X", "dx": "S72"}


def _login(user):
    assert client.post("/api/auth/login", json={"username": user, "password": user}).status_code == 200


def _claim(cid, party, cas, **kw):
    return {"claim_id": cid, "claim_type": "SUPPLIER", "party_token": party,
            "accident_date": "2026-02-01", "lodged_on": "2026-03-01", "case_number_raw": cas,
            "today": "2026-07-05", "payee_verified": True,
            "documents": {"RAF2": True, "OAR": True, "INVOICES": True, "BANK": True},
            "lines": [dict(LINE)], **kw}


def _personal(cid, party, cas, **kw):
    return _claim(cid, party, cas, claim_type="PERSONAL", merits_accepted=True,
                  documents={"RAF1": True, "OAR": True, "ID": True, "BANK": True}, **kw)


def _submit(body):
    r = client.post("/api/claims", json=body)
    assert r.status_code == 200, r.text
    return r.json()


# ── H1 ─────────────────────────────────────────────────────────────────────────────────────────
def test_h1_three_calendar_years_across_a_leap_day_is_in_time():
    _login("handler")
    d = _submit(_personal("R_x1", "P_x1", "CAS 9801/03/2024",
                          accident_date="2024-03-01", lodged_on="2027-03-01"))
    assert "PRESCRIBED_LODGEMENT" not in d["reasons"]
    d2 = _submit(_personal("R_x1b", "P_x1b", "CAS 9802/03/2024",
                           accident_date="2024-03-01", lodged_on="2027-03-02"))
    assert "PRESCRIBED_LODGEMENT" in d2["reasons"] and d2["disposition"] == "COMPLIANCE"


# ── H2 ─────────────────────────────────────────────────────────────────────────────────────────
def test_h2_same_service_on_a_second_claim_is_supplier_preclusion():
    _login("handler")
    first = _submit(_claim("R_x2a", "P_x2", "CAS 9803/02/2026"))
    assert first["medical_payable"] == 500.0 and first["reasons"] == []
    # the same party, provider, date, code and amount billed again on another claim: pay once
    again = _submit(_claim("R_x2b", "P_x2", "CAS 9803/02/2026",
                           lines=[dict(LINE), {**LINE, "amount": 300.0}]))
    assert again["reasons"] == ["SUPPLIER_PRECLUSION"] and again["disposition"] == "ADJUSTED"
    assert again["medical_payable"] == 300.0                 # only the new service pays
    # a leading-zero variant of the paid code is the same service (H3 + H2 together)
    variant = _submit(_claim("R_x2c", "P_x2", "CAS 9803/02/2026",
                             lines=[{**LINE, "code": "190"}]))
    assert variant["reasons"] == ["SUPPLIER_PRECLUSION"] and variant["medical_payable"] == 0.0


def test_h2_unpaid_prior_line_does_not_preclude():
    _login("handler")
    # the first line never paid (service before accident) -> not in the pay-once ledger
    _submit(_claim("R_x2d", "P_x2d", "CAS 9804/02/2026",
                   lines=[{**LINE, "service_date": "2026-01-15"}]))
    second = _submit(_claim("R_x2e", "P_x2d", "CAS 9804/02/2026",
                            lines=[{**LINE, "service_date": "2026-01-15"}]))
    assert second["reasons"] == ["SERVICE_BEFORE_ACCIDENT"]   # its own gate, not preclusion


def test_h2_second_personal_claim_by_same_claimant_on_same_accident_is_duplicate_claim():
    _login("handler")
    a = _submit(_personal("R_x2f", "P_x2f", "CAS 9805/02/2026"))
    assert "DUPLICATE_CLAIM" not in a["reasons"]
    b = _submit(_personal("R_x2g", "P_x2f", "CAS 9805/02/2026",
                          lines=[{**LINE, "service_date": "2026-03-05"}]))
    assert b["accident_id"] == a["accident_id"] and b["accident_action"] == "JOINED"
    assert "DUPLICATE_CLAIM" in b["reasons"] and b["disposition"] == "COMPLIANCE"
    assert b["eligible_to_pay"] is False
    # a SUPPLIER claim for that claimant on the same accident is not a duplicate claim
    s = _submit(_claim("R_x2h", "P_x2f", "CAS 9805/02/2026",
                       lines=[{**LINE, "service_date": "2026-03-06"}]))
    assert "DUPLICATE_CLAIM" not in s["reasons"]


def test_h2_rescore_does_not_flag_the_claim_as_its_own_duplicate():
    _login("handler")
    _submit(_personal("R_x2i", "P_x2i", "CAS 9806/02/2026"))
    _login("admin")
    r = client.post("/api/claims/R_x2i/rescore", json={})
    assert r.status_code == 200
    assert "DUPLICATE_CLAIM" not in r.json()["reasons"] and "SUPPLIER_PRECLUSION" not in r.json()["reasons"]


# ── H3 ─────────────────────────────────────────────────────────────────────────────────────────
def test_h3_leading_zero_variants_are_one_duplicate_line():
    _login("handler")
    d = _submit(_claim("R_x3", "P_x3", "CAS 9807/02/2026",
                       lines=[dict(LINE), {**LINE, "code": "190"}]))
    assert d["reasons"] == ["DUPLICATE_LINE"] and d["medical_payable"] == 500.0


# ── H5 ─────────────────────────────────────────────────────────────────────────────────────────
def test_h5_advisory_signal_is_visible_but_never_routes():
    _login("admin")
    try:
        assert client.post("/api/admin/signal-modes",
                           json={"code": "DX_ACCIDENT_MISMATCH", "mode": "ADVISORY"}).status_code == 200
        _login("handler")
        d = _submit(_claim("R_x5", "P_x5", "CAS 9808/02/2026", accident_dx_regions=["S72"],
                           lines=[{**LINE, "dx": "K35"}]))
        assert d["reasons"] == ["DX_ACCIDENT_MISMATCH"] and d["advisory_signals"] == ["DX_ACCIDENT_MISMATCH"]
        assert d["score"] == 0 and d["disposition"] == "CLEAN" and d["eligible_to_pay"] is True
        stored = client.get("/api/claims/R_x5").json()["determination"]
        assert stored["advisory_signals"] == ["DX_ACCIDENT_MISMATCH"]
    finally:
        _login("admin")
        client.delete("/api/admin/signal-modes/DX_ACCIDENT_MISMATCH")


def test_h5_single_scored_heuristic_below_amber_does_not_hold_payment():
    _login("handler")
    d = _submit(_claim("R_x5b", "P_x5b", "CAS 9809/02/2026", accident_dx_regions=["S72"],
                       lines=[{**LINE, "dx": "K35"}]))
    assert d["reasons"] == ["DX_ACCIDENT_MISMATCH"] and d["score"] == 15 and d["band"] == "GREEN"
    assert d["disposition"] == "CLEAN" and d["eligible_to_pay"] is True


# ── H6 ─────────────────────────────────────────────────────────────────────────────────────────
def test_h6_uncovered_code_is_held_for_review_and_flagged_everywhere():
    _login("handler")
    d = _submit(_claim("R_x6", "P_x6", "CAS 9810/02/2026",
                       lines=[{**LINE, "code": "7777", "amount": 99_000_000.0}]))
    assert d["needs_review"] is True and d["reasons"] == ["REFERENCE_UNRESOLVED"]
    assert d["disposition"] == "REVIEW" and d["eligible_to_pay"] is False and "held_review" in d["holds"]
    stored = client.get("/api/claims/R_x6").json()["determination"]
    assert stored["needs_review"] is True and stored["disposition"] == "REVIEW"
    flagged = client.get("/api/claims", params={"needs_review": "true", "q": "R_x6"}).json()
    assert [x["claim_id"] for x in flagged] == ["R_x6"]
    assert client.get("/api/dashboard").json()["needs_review"] >= 1
    assert all(row["claim_id"] != "R_x6" for row in client.get("/api/payments/queue").json())


# ── H7 ─────────────────────────────────────────────────────────────────────────────────────────
def test_h7_accident_ids_derive_from_the_claim_and_worklist_never_joins():
    _login("handler")
    a = _submit(_claim("R_x7a", "P_x7", "CAS 9811/02/2026"))
    assert a["accident_action"] == "CREATED" and a["accident_id"] == "A_R_x7a"
    # same party, same date, no CAS -> fuzzy 0.55 (date + party) -> WORKLIST, not a join
    b = _submit(_claim("R_x7b", "P_x7", None, lines=[{**LINE, "service_date": "2026-03-02"}]))
    assert b["accident_action"] == "WORKLIST" and b["accident_id"] == "A_R_x7b"
    assert b["accident_candidate"] == "A_R_x7a"
    acc_a = client.get("/api/accidents/A_R_x7a").json()
    acc_b = client.get("/api/accidents/A_R_x7b").json()
    assert acc_a["claims"] == ["R_x7a"] and acc_b["claims"] == ["R_x7b"]
    assert client.get("/api/claims/R_x7b").json()["determination"]["accident_candidate"] == "A_R_x7a"


# ── H8 ─────────────────────────────────────────────────────────────────────────────────────────
def test_h8_stored_shadow_override_on_a_grounded_gate_is_ignored_by_the_engine():
    db = SessionLocal()
    try:
        db.add(models.RefSignalMode(code="PRESCRIBED_LODGEMENT", mode="SHADOW",
                                    effective_from=date(2026, 1, 1), set_by="rogue"))
        db.commit()
        _login("handler")
        d = _submit(_personal("R_x8", "P_x8", "CAS 9812/01/2020",
                              accident_date="2020-01-01", lodged_on="2024-01-01"))
        assert "PRESCRIBED_LODGEMENT" in d["reasons"]
        assert "PRESCRIBED_LODGEMENT" not in d["shadow_signals"]
        assert d["disposition"] == "COMPLIANCE" and d["eligible_to_pay"] is False
    finally:
        db.query(models.RefSignalMode).filter_by(code="PRESCRIBED_LODGEMENT").delete()
        db.commit()
        db.close()


# ── H9 ─────────────────────────────────────────────────────────────────────────────────────────
def test_h9_dashboard_and_list_count_each_claim_once_by_its_latest_determination():
    _login("handler")
    _submit(_claim("R_x9", "P_x9", "CAS 9813/02/2026"))
    before = client.get("/api/dashboard").json()
    listed = client.get("/api/claims", params={"q": "R_x9"})
    assert listed.headers["X-Total-Count"] == "1" and len(listed.json()) == 1
    _login("admin")
    for _ in range(3):
        assert client.post("/api/claims/R_x9/rescore", json={}).status_code == 200
    after = client.get("/api/dashboard").json()
    assert after["determinations"] == before["determinations"]
    assert after["net_payable_total"] == before["net_payable_total"]
    assert after["eligible_to_pay"] == before["eligible_to_pay"]
    listed = client.get("/api/claims", params={"q": "R_x9"})
    assert listed.headers["X-Total-Count"] == "1" and len(listed.json()) == 1
    with SessionLocal() as db:
        n = db.query(models.Determination).filter_by(claim_id="R_x9").count()
    assert n == 4                                            # the history is kept, just not counted twice
    assert listed.json()[0]["id"] == client.get("/api/claims/R_x9").json()["determination"]["id"]


def test_h9_list_pages_through_the_whole_corpus_with_a_real_total():
    _login("handler")
    for i in range(3):
        _submit(_claim(f"R_x9p{i}", f"P_x9p{i}", f"CAS 98{20 + i}/02/2026"))
    page = client.get("/api/claims", params={"q": "R_x9p", "limit": 2, "offset": 0})
    assert page.headers["X-Total-Count"] == "3" and len(page.json()) == 2
    rest = client.get("/api/claims", params={"q": "R_x9p", "limit": 2, "offset": 2})
    assert rest.headers["X-Total-Count"] == "3" and len(rest.json()) == 1


def test_h9_precision_counts_one_firing_per_claim():
    from server.precision_service import precision_by_signal
    _login("handler")
    _submit(_claim("R_x9q", "P_x9q", "CAS 9830/02/2026", accident_dx_regions=["S72"],
                   lines=[{**LINE, "dx": "K35"}]))
    with SessionLocal() as db:
        before = {r["signal"]: r["fired"] for r in precision_by_signal(db)}["DX_ACCIDENT_MISMATCH"]
    _login("admin")
    assert client.post("/api/claims/R_x9q/rescore", json={}).status_code == 200
    with SessionLocal() as db:
        after = {r["signal"]: r["fired"] for r in precision_by_signal(db)}["DX_ACCIDENT_MISMATCH"]
    assert after == before


# ── H11 ────────────────────────────────────────────────────────────────────────────────────────
def test_h11_pii_is_stripped_at_every_depth():
    p = pseudonymise_ingest({
        "claim_id": "R_pii", "id_number": "9001010001088", "attorney": "ATT_7",
        "lines": [{**LINE, "patient_name": "Jane Doe", "patient_phone": "0821234567",
                   "claimant_surname": "Doe"}],
        "undertaking": {"active": True, "scope_dx": ["S72"], "scope_coded": True,
                        "beneficiary_name": "Jane", "authorisations": [
                            {"codes": ["0190"], "ceiling": 1000, "valid_from": "2026-01-01",
                             "valid_to": "2026-12-31", "approved_by_name": "Dr X"}]},
        "notes": {"contact_email": "jane@example.com", "ref": "ok", "other_id": "9001010001088"},
    })
    assert p["party_token"] == token("9001010001088", "P")
    assert "id_number" not in p and p["attorney"] == "ATT_7"           # extras survive, PII does not
    assert set(p["lines"][0]) == set(LINE)                             # typed structure: declared fields only
    assert set(p["undertaking"]) == {"active", "scope_dx", "scope_coded", "authorisations"}
    assert set(p["undertaking"]["authorisations"][0]) == {"codes", "ceiling", "valid_from", "valid_to"}
    assert p["notes"] == {"ref": "ok", "other_id": token("9001010001088", "P")}   # raw ID tokenised anywhere


def test_h11_nested_pii_never_reaches_the_stored_payload():
    _login("handler")
    body = _claim("R_x11", "P_x11", "CAS 9831/02/2026",
                  lines=[{**LINE, "patient_name": "Jane Doe"}], extra={"next_of_kin_name": "John"})
    _submit(body)
    raw = client.get("/api/claims/R_x11").json()["claim"]["raw"]
    assert "patient_name" not in raw["lines"][0] and raw["extra"] == {}
    assert "Jane" not in str(raw) and "John" not in str(raw)


def test_h11_pipeline_refuses_a_raw_identity_number_as_party_token():
    from server.pipeline_service import assess_and_store
    import pytest
    with SessionLocal() as db, pytest.raises(ValueError):
        assess_and_store(db, _claim("R_x11b", "8001015009087", "CAS 9832/02/2026"))


# ── H12 ────────────────────────────────────────────────────────────────────────────────────────
def test_h12_money_is_rounded_half_up_through_the_api():
    _login("handler")
    d = _submit(_personal("R_x12", "P_x12", "CAS 9833/02/2026", fault_pct=30.0,
                          lines=[{**LINE, "amount": 100.05}]))
    assert d["medical_payable"] == 70.04 and d["net_payable"] == 70.04
    stored = client.get("/api/claims/R_x12").json()["determination"]
    assert stored["medical_payable"] == 70.04
