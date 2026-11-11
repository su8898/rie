"""The practice register (port of CIE's provider identity registry): who a billing practice is,
and whether it may bill. At intake the register, not the submitter, decides registration,
discipline and setting."""
from __future__ import annotations

import time
import uuid

import test_api  # noqa: F401  (sets RIE_DATABASE_URL + imports the app first)
from fastapi.testclient import TestClient
from sqlalchemy import select

from server import config, jws, models, provider_registry_service as svc
from server.db import SessionLocal
from server.main import app

ops = TestClient(app)
net = TestClient(app)
ADMIN = {"username": "admin", "role": "ADMIN"}


def _login(user="admin"):
    assert ops.post("/api/auth/login", json={"username": user, "password": user}).status_code == 200


def _practice(provider_id, **fields):
    _login()
    r = ops.post("/api/admin/practices", json={"provider_id": provider_id, **fields})
    assert r.status_code == 200, r.text
    return r.json()


def _status(provider_id, status, reason=""):
    _login()
    return ops.post(f"/api/admin/practices/{provider_id}/status", json={"status": status, "reason": reason})


def _claim(cid, provider, amount=500.0, discipline=None, **kw):
    line = {"kind": "TARIFF", "code": "0190", "qty": 1, "amount": amount, "service_date": "2026-03-01",
            "provider_id": provider, "dx": "S72"}
    if discipline is not None:
        line["discipline"] = discipline
    return {"claim_id": cid, "claim_type": "SUPPLIER", "party_token": f"P_{cid}",
            "accident_date": "2026-02-01", "lodged_on": "2026-03-01", "case_number_raw": "CAS 8700/02/2026",
            "today": "2026-07-05", "payee_verified": True,
            "documents": {"RAF2": True, "OAR": True, "INVOICES": True, "BANK": True}, "lines": [line], **kw}


def _submit(*args, **kw):
    _login("handler")
    r = ops.post("/api/claims", json=_claim(*args, **kw))
    assert r.status_code == 200, r.text
    return r.json()


def _raw(cid):
    with SessionLocal() as db:
        return db.get(models.ClaimRecord, cid).raw


# ── maintenance ──────────────────────────────────────────────────────────────
def test_reads_are_for_operators_and_changes_for_admin():
    assert TestClient(app).get("/api/practices").status_code == 401
    _login("handler")
    assert ops.get("/api/practices").status_code == 200 and ops.get("/api/practices/summary").status_code == 200
    assert ops.post("/api/admin/practices", json={"provider_id": "PRG_X"}).status_code == 403
    assert ops.post("/api/admin/practices/PRG_X/status", json={"status": "SUSPENDED"}).status_code == 403
    assert ops.post("/api/admin/practices/import", json={"csv": "provider_id\nX"}).status_code == 403


def test_add_update_search_and_identity():
    made = _practice("PRG_1", practice_name="  Acme Physio ", discipline="Physiotherapy",
                     practice_type="group", setting="rooms", professional_nr="PT0012345",
                     status="SUSPENDED", source="PCNS", commit=False)        # the last three are not settable
    assert (made["practice_name"], made["practice_type"], made["setting"]) == ("Acme Physio", "GROUP", "ROOMS")
    assert (made["status"], made["source"], made["verified"], made["updated_by"]) == ("ACTIVE", "MANUAL", True, "admin")
    again = _practice("PRG_1", practice_name="Acme Physiotherapy")            # an update, other fields kept
    assert again["practice_name"] == "Acme Physiotherapy" and again["discipline"] == "Physiotherapy"
    _practice("PRG_2", practice_name="Beta Radiology", discipline="Radiology", setting="HOSPITAL")

    _login("handler")
    hit = ops.get("/api/practices", params={"q": "acme"}).json()
    assert hit["total"] == 1 and hit["items"][0]["provider_id"] == "PRG_1"
    assert ops.get("/api/practices", params={"q": "PRG_", "page_size": 1, "page": 2}).json()["items"][0]["provider_id"] == "PRG_2"
    assert ops.get("/api/practices", params={"q": "PRG_", "status": "SUSPENDED"}).json()["total"] == 0
    known = ops.get("/api/practices/PRG_1").json()
    assert known["known"] is True and known["may_bill"] is True and known["discipline"] == "Physiotherapy"
    assert ops.get("/api/practices/PRG_NOBODY").json() == {"provider_id": "PRG_NOBODY", "known": False, "may_bill": True}
    with SessionLocal() as db:
        actions = [a.action for a in db.scalars(select(models.AdminAudit).where(models.AdminAudit.target == "PRG_1"))]
    assert actions == ["provider_register.add", "provider_register.update"]


def test_validation():
    _login()

    def bad(**body):
        r = ops.post("/api/admin/practices", json=body)
        assert r.status_code == 400, r.text
        return r.json()["detail"]

    assert "practice number is required" in bad(provider_id=" ")
    assert "practice number is required" in bad(provider_id="x" * 65)
    assert "practice type must be one of" in bad(provider_id="PRG_V", practice_type="CLINIC")
    assert "setting must be one of" in bad(provider_id="PRG_V", setting="THEATRE")
    assert ops.get("/api/practices/PRG_V").json()["known"] is False


def test_status_needs_a_reason_to_bar_and_none_to_reinstate():
    _practice("PRG_S1")
    assert "reason is required" in _status("PRG_S1", "SUSPENDED").json()["detail"]
    assert "status must be one of" in _status("PRG_S1", "BANNED", "x").json()["detail"]
    assert "not in the register" in _status("PRG_NOBODY", "SUSPENDED", "x").json()["detail"]
    barred = _status("PRG_S1", "SUSPENDED", "HPCSA suspension 2026/11").json()
    assert (barred["status"], barred["status_reason"]) == ("SUSPENDED", "HPCSA suspension 2026/11")
    _login("handler")
    assert ops.get("/api/practices/PRG_S1").json()["may_bill"] is False
    back = _status("PRG_S1", "ACTIVE").json()
    assert (back["status"], back["status_reason"]) == ("ACTIVE", "")
    with SessionLocal() as db:
        last = list(db.scalars(select(models.AdminAudit).where(models.AdminAudit.target == "PRG_S1")))[-1]
    assert last.action == "provider_register.status" and last.detail == {"from": "SUSPENDED", "to": "ACTIVE", "reason": ""}


# ── intake: registration ─────────────────────────────────────────────────────
def test_suspended_practice_cannot_bill_whatever_the_submitter_says():
    _practice("PRG_BAR")
    assert _submit("R_PRG_OK", "PRG_BAR")["eligible_to_pay"] is True
    _status("PRG_BAR", "SUSPENDED", "under investigation")

    det = _submit("R_PRG_BAR", "PRG_BAR", provider_registered=True)           # the operator payload says registered
    assert "PROVIDER_UNREGISTERED" in det["reasons"] and det["eligible_to_pay"] is False
    assert det["disposition"] == "COMPLIANCE"
    raw = _raw("R_PRG_BAR")
    assert raw["provider_registered"] is False and raw["provider_register_barred"] == ["PRG_BAR"]

    # the same over the provider channel, where the flag cannot be asserted at all
    body = _claim("R_PRG_BAR_RAILS", "PRG_BAR")
    sig = jws.sign_detached({"alg": "HS256", "jti": str(uuid.uuid4()), "exp": int(time.time()) + 300},
                            body, "rie-rails-dev-secret")
    v = net.post("/rails/v1/claims", json=body, headers={"Idempotency-Key": str(uuid.uuid4()),
                                                         "X-JWS-Signature": sig}).json()["verdict"]
    assert "PROVIDER_UNREGISTERED" in v["reasons"] and v["outcome"] == "HELD"

    _status("PRG_BAR", "DEREGISTERED", "practice closed")
    assert "PROVIDER_UNREGISTERED" in _submit("R_PRG_BAR2", "PRG_BAR")["reasons"]
    _status("PRG_BAR", "ACTIVE")
    assert _submit("R_PRG_BAR3", "PRG_BAR")["reasons"] == []                   # reinstated


def test_one_barred_practice_on_a_claim_bars_the_claim():
    _practice("PRG_MIX_BAD")
    _status("PRG_MIX_BAD", "SUSPENDED", "x")
    body = _claim("R_PRG_MIX", "PRG_MIX_GOOD")
    body["lines"].append({**body["lines"][0], "provider_id": "PRG_MIX_BAD", "amount": 400.0})
    _login("handler")
    det = ops.post("/api/claims", json=body).json()
    assert "PROVIDER_UNREGISTERED" in det["reasons"]
    assert _raw("R_PRG_MIX")["provider_register_barred"] == ["PRG_MIX_BAD"]


def test_unknown_practice_is_accepted_unless_enforcement_is_on(monkeypatch):
    assert _submit("R_PRG_UNK1", "PRG_NEVER_SEEN")["reasons"] == []
    assert "provider_register_barred" not in _raw("R_PRG_UNK1")
    _practice("PRG_ENF_KNOWN")
    monkeypatch.setattr(config, "PROVIDER_REGISTER_ENFORCED", True)
    assert "PROVIDER_UNREGISTERED" in _submit("R_PRG_UNK2", "PRG_NEVER_SEEN")["reasons"]
    assert _submit("R_PRG_UNK3", "PRG_ENF_KNOWN")["reasons"] == []
    _login("handler")
    assert ops.get("/api/practices/PRG_NEVER_SEEN").json()["may_bill"] is False
    assert ops.get("/api/practices/summary").json()["enforced"] is True
    monkeypatch.setattr(config, "PROVIDER_REGISTER_ENFORCED", False)
    s = ops.get("/api/practices/summary").json()
    assert s["enforced"] is False and s["total"] == sum(s["by_status"].values()) >= 1


def test_a_rescore_keeps_the_facts_fixed_at_submission():
    _practice("PRG_RESCORE")
    assert _submit("R_PRG_RESC", "PRG_RESCORE")["reasons"] == []
    _status("PRG_RESCORE", "SUSPENDED", "later event")
    _login()
    r = ops.post("/api/claims/R_PRG_RESC/rescore")
    assert r.status_code == 200 and "PROVIDER_UNREGISTERED" not in r.json()["reasons"]


# ── intake: discipline and setting ───────────────────────────────────────────
def test_lines_are_priced_under_the_registered_discipline():
    # the seeded tariff prices code 0190 at R500 for a GP and R700 for a SPECIALIST
    _practice("PRG_SPEC", discipline="SPECIALIST")
    det = _submit("R_PRG_D1", "PRG_SPEC", amount=700.0)                        # no discipline on the line
    assert det["medical_payable"] == 700.0 and det["reasons"] == []
    assert _raw("R_PRG_D1")["lines"][0]["discipline"] == "SPECIALIST"
    assert "discipline_asserted" not in _raw("R_PRG_D1")["lines"][0]

    _practice("PRG_GP", discipline="GP")
    over = _submit("R_PRG_D2", "PRG_GP", amount=700.0, discipline="SPECIALIST")   # claims the dearer discipline
    assert over["medical_payable"] == 500.0 and "BILLED_OVER_REFERENCE" in over["reasons"]
    line = _raw("R_PRG_D2")["lines"][0]
    assert (line["discipline"], line["discipline_asserted"]) == ("GP", "SPECIALIST")

    same = _submit("R_PRG_D3", "PRG_GP", discipline="GP")                      # already right: untouched
    assert same["reasons"] == [] and "discipline_asserted" not in _raw("R_PRG_D3")["lines"][0]

    _practice("PRG_UNVERIFIED", discipline="GP", verified=False)               # an unverified row decides nothing
    kept = _submit("R_PRG_D4", "PRG_UNVERIFIED", amount=700.0, discipline="SPECIALIST")
    assert kept["medical_payable"] == 700.0 and _raw("R_PRG_D4")["lines"][0]["discipline"] == "SPECIALIST"


def test_setting_decides_whether_a_claim_is_a_facility_account():
    _practice("PRG_HOSP", setting="HOSPITAL")
    _practice("PRG_ER", setting="ER")
    _practice("PRG_ROOMS", setting="ROOMS")
    _practice("PRG_MIXED", setting="MIXED")
    _submit("R_PRG_F1", "PRG_HOSP")
    assert _raw("R_PRG_F1")["facility"] is True                               # derived, not asserted
    _submit("R_PRG_F2", "PRG_ROOMS", facility=True)
    assert _raw("R_PRG_F2")["facility"] is False                              # rooms practice cannot claim to be a hospital
    _submit("R_PRG_F3", "PRG_MIXED", facility=True)
    assert _raw("R_PRG_F3")["facility"] is True                               # undecided: as submitted
    _submit("R_PRG_F4", "PRG_NEVER_SEEN_2", facility=True)
    assert _raw("R_PRG_F4")["facility"] is True

    both = _claim("R_PRG_F5", "PRG_HOSP")
    both["lines"].append({**both["lines"][0], "provider_id": "PRG_ER", "amount": 400.0})
    half = _claim("R_PRG_F6", "PRG_HOSP")
    half["lines"].append({**half["lines"][0], "provider_id": "PRG_NEVER_SEEN_3", "amount": 400.0})
    _login("handler")
    assert ops.post("/api/claims", json=both).status_code == 200 and _raw("R_PRG_F5")["facility"] is True
    assert ops.post("/api/claims", json=half).status_code == 200 and "facility" not in _raw("R_PRG_F6")


def test_a_claim_without_lines_is_left_alone():
    payload = {"claim_id": "X", "lines": []}
    with SessionLocal() as db:
        assert svc.apply(db, payload) is payload


# ── import and the live-feed seam ────────────────────────────────────────────
def test_csv_import_loads_good_rows_reports_bad_ones_and_never_changes_status():
    _practice("PRG_CSV_1", practice_name="Old name")
    _status("PRG_CSV_1", "SUSPENDED", "x")
    _login()
    csv = ("provider_id,practice_name,discipline,setting,status\n"
           "PRG_CSV_1,New name,GP,ROOMS,ACTIVE\n"
           "PRG_CSV_2,Second,Physiotherapy,hospital,\n"
           "PRG_CSV_3,Third,GP,BASEMENT,\n"
           ",No number,GP,ROOMS,\n")
    out = ops.post("/api/admin/practices/import", json={"csv": csv}).json()
    assert out["loaded"] == 2 and [e["line"] for e in out["errors"]] == [4, 5]
    assert "setting must be one of" in out["errors"][0]["error"]
    _login("handler")
    one = ops.get("/api/practices/PRG_CSV_1").json()
    assert (one["practice_name"], one["status"], one["source"]) == ("New name", "SUSPENDED", "IMPORT")
    assert ops.get("/api/practices/PRG_CSV_2").json()["setting"] == "HOSPITAL"
    assert ops.get("/api/practices/PRG_CSV_3").json()["known"] is False
    _login()
    for bad in ("", "name,discipline\nA,B\n"):
        r = ops.post("/api/admin/practices/import", json={"csv": bad})
        assert r.status_code == 400 and "provider_id column" in r.json()["detail"]


def test_import_refuses_an_oversized_file(monkeypatch):
    monkeypatch.setattr(svc, "MAX_IMPORT", 2)
    _login()
    r = ops.post("/api/admin/practices/import", json={"csv": "provider_id\nPRG_BIG_1\nPRG_BIG_2\nPRG_BIG_3\n"})
    assert r.status_code == 400 and "at most 2 rows" in r.json()["detail"]


def test_live_feed_seam_is_inert_until_a_feed_is_connected():
    class Feed(svc.RegisterFeed):
        AVAILABLE = True

        def __init__(self, data):
            self.data = data

        def lookup(self, practice_number):
            return self.data

    with SessionLocal() as db:
        assert svc.sync(db, ADMIN, "PRG_FEED") is None                        # no feed: nothing happens
        assert svc.sync(db, ADMIN, "PRG_FEED", Feed(None)) is None            # the feed does not know it
        row = svc.sync(db, ADMIN, "PRG_FEED", Feed({"practice_name": "From the feed", "discipline": "GP"}))
        assert (row["practice_name"], row["source"], row["status"]) == ("From the feed", "PCNS", "ACTIVE")
