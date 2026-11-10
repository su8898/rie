"""Dated reference rates (port of CIE's effective-dated rate store).

A rate is an append-only version; a later version supersedes the prior one from its effective
date; the engine prices each line at the version in force on its SERVICE date. These tests use
their own tariff / NAPPI codes (91xx / T91xx) so the shared seeded reference is never disturbed."""
from __future__ import annotations

from datetime import date

import test_api  # noqa: F401  (sets RIE_DATABASE_URL + imports the app first)
from fastapi.testclient import TestClient
from sqlalchemy import select

import engine
from server import models, rates_service as svc
from server.db import SessionLocal
from server.main import app
from server.reference_data import build_refbook

client = TestClient(app)
ADMIN = {"username": "admin", "role": "ADMIN"}


def _login(user="admin"):
    assert client.post("/api/auth/login", json={"username": user, "password": user}).status_code == 200


def _add(code, rate, eff, discipline="GP", source="RPL", **kw):
    return client.post("/api/rates", json={"source": source, "code": code, "discipline": discipline,
                                           "rate": rate, "effective_from": eff, **kw})


def _current(code, on=None, source="RPL", **params):
    q = {"source": source, "q": code, **params}
    if on:
        q["on"] = on
    return client.get("/api/rates", params=q).json()


def _claim(cid, party, cas, lines, accident="2026-02-01"):
    return {"claim_id": cid, "claim_type": "SUPPLIER", "party_token": party,
            "accident_date": accident, "lodged_on": "2026-03-01", "case_number_raw": cas,
            "today": "2026-07-05", "payee_verified": True,
            "documents": {"RAF2": True, "OAR": True, "INVOICES": True, "BANK": True},
            "lines": lines}


def _line(code, amount, svc, kind="TARIFF"):
    return {"kind": kind, "code": code, "qty": 1, "amount": amount, "service_date": svc,
            "provider_id": "PR_RATES", "dx": "S72"}


# ── access ───────────────────────────────────────────────────────────────────
def test_rates_need_a_session_and_maintenance_needs_admin():
    anon = TestClient(app)
    assert anon.get("/api/rates").status_code == 401
    assert anon.post("/api/rates", json={}).status_code == 401
    _login("handler")
    assert client.get("/api/rates").status_code == 200
    assert client.get("/api/rates/summary").status_code == 200
    assert _add("9100", 100, "2026-01-01").status_code == 403
    for path, body in (("/api/rates/increase", {"source": "RPL", "code": "9100", "discipline": "GP",
                                                "pct": 5, "effective_from": "2027-01-01"}),
                       ("/api/rates/bulk-increase", {"source": "RPL", "pct": 5, "effective_from": "2027-01-01"}),
                       ("/api/rates/import", {"csv": "code,rate,effective_from\n1,1,2026-01-01"}),
                       ("/api/rates/1/adjust", {"rate": 1}), ("/api/rates/1/retire", {"effective_to": "2026-01-01"})):
        assert client.post(path, json=body).status_code == 403, path


# ── versions and supersession ────────────────────────────────────────────────
def test_create_then_supersede_closes_the_prior_version_the_day_before():
    _login()
    v1 = _add("9101", 300, "2025-01-01", note="gazette 2025")
    assert v1.status_code == 200 and v1.json()["action"] == "CREATE"
    v2 = _add("09101", 330, "2026-01-01")                       # leading zero = the same code
    assert v2.json()["action"] == "SUPERSEDE" and v2.json()["code"] == "9101"

    vs = client.get("/api/rates/versions", params={"source": "RPL", "code": "9101", "discipline": "GP"}).json()
    assert [(v["rate"], v["effective_from"], v["effective_to"]) for v in vs] == [
        (330.0, "2026-01-01", None), (300.0, "2025-01-01", "2025-12-31")]

    assert _current("9101", on="2025-06-30")["items"][0]["rate"] == 300.0
    assert _current("9101", on="2026-06-30")["items"][0]["rate"] == 330.0
    assert _current("9101", on="2024-06-30")["items"][0]["rate"] is None     # before the first version
    now = _current("9101")["items"][0]
    assert now["rate"] == 330.0 and now["versions"] == 2 and now["dated"] is True

    with SessionLocal() as db:                                   # the undated table tracks today's rate
        assert db.get(models.RefRpl, ("9101", "GP")).rate == 330.0
        acts = [r.action for r in db.scalars(select(models.RefRateLog).where(models.RefRateLog.code == "9101")
                                             .order_by(models.RefRateLog.id))]
        assert acts == ["CREATE", "SUPERSEDE"]
        assert db.scalar(select(models.AdminAudit).where(models.AdminAudit.action == "rate.supersede",
                                                         models.AdminAudit.target == "RPL:TARIFF:9101:GP")) is not None


def test_maintenance_is_forward_only():
    _login()
    assert _add("9101", 999, "2026-01-01").status_code == 409              # same start date
    r = _add("9101", 999, "2025-06-01")                                    # before the newest version
    assert r.status_code == 409 and "later effective date" in r.json()["detail"]


def test_first_dated_change_keeps_the_undated_rate_as_a_baseline_version():
    with SessionLocal() as db:
        db.add(models.RefRpl(code="9102", discipline="GP", rate=200.0))
        db.commit()
    _login()
    before = client.get("/api/rates/versions", params={"source": "RPL", "code": "9102", "discipline": "GP"}).json()
    assert before == [{"id": None, "source": "RPL", "kind": "TARIFF", "code": "9102", "discipline": "GP",
                       "rate": 200.0, "effective_from": None, "effective_to": None, "origin": "undated",
                       "note": "", "created_by": ""}]
    assert _add("9102", 220, "2026-06-01").json()["action"] == "SUPERSEDE"
    vs = client.get("/api/rates/versions", params={"source": "RPL", "code": "9102", "discipline": "GP"}).json()
    assert [(v["rate"], v["effective_from"], v["effective_to"], v["origin"]) for v in vs] == [
        (220.0, "2026-06-01", None, "manual"), (200.0, "1900-01-01", "2026-05-31", "baseline")]
    lg = client.get("/api/rates/log", params={"code": "9102"}).json()
    assert lg[0]["action"] == "SUPERSEDE" and lg[0]["old_rate"] == 200.0 and lg[0]["new_rate"] == 220.0
    assert lg[0]["changed_by"] == "admin"
    assert _current("9102", on="2026-05-31")["items"][0]["rate"] == 200.0
    assert _current("9102", on="2026-06-01")["items"][0]["rate"] == 220.0


# ── pricing follows the service date ─────────────────────────────────────────
def test_a_claim_is_priced_at_the_rate_in_force_on_each_service_date():
    _login()
    late = client.post("/api/claims", json=_claim(
        "R_RATE_LATE", "P_RATE_1", "CAS 9101/06/2025",
        [_line("9101", 330.0, "2025-07-01")], accident="2025-06-01"))
    assert late.status_code == 200, late.text
    det = late.json()
    assert det["medical_payable"] == 300.0 and "BILLED_OVER_REFERENCE" in det["reasons"]

    current = client.post("/api/claims", json=_claim(
        "R_RATE_NOW", "P_RATE_2", "CAS 9102/02/2026", [_line("9101", 330.0, "2026-03-01")])).json()
    assert current["medical_payable"] == 330.0 and current["reasons"] == []

    with SessionLocal() as db:                                   # the stored reference is the dated one
        refs = {r.claim_id: r.reference for r in db.scalars(select(models.BillingLineRecord).where(
            models.BillingLineRecord.claim_id.in_(["R_RATE_LATE", "R_RATE_NOW"])))}
    assert refs == {"R_RATE_LATE": 300.0, "R_RATE_NOW": 330.0}


def test_refbook_carries_versions_for_dated_keys_and_plain_rates_otherwise():
    with SessionLocal() as db:
        book = build_refbook(db, nappi_codes=set())
    assert book.rpl["9101"]["GP"] == [(date(2025, 1, 1), date(2025, 12, 31), 300.0),
                                      (date(2026, 1, 1), None, 330.0)]
    assert book.rpl["190"]["GP"] == 500.0                        # seeded, undated: untouched
    assert engine.resolve(book, "TARIFF", "9101", "GP", date(2025, 3, 1))[0] == 300.0


# ── increases ────────────────────────────────────────────────────────────────
def test_percentage_increase_supersedes_from_a_future_date():
    _login()
    r = client.post("/api/rates/increase", json={"source": "RPL", "code": "9101", "discipline": "GP",
                                                 "pct": 10, "effective_from": "2099-01-01"})
    assert r.status_code == 200 and r.json()["rate"] == 363.0 and r.json()["action"] == "SUPERSEDE"
    assert _current("9101", on="2099-06-01")["items"][0]["rate"] == 363.0
    assert _current("9101")["items"][0]["rate"] == 330.0         # not yet in force
    with SessionLocal() as db:
        assert db.get(models.RefRpl, ("9101", "GP")).rate == 330.0
    nothing = client.post("/api/rates/increase", json={"source": "RPL", "code": "9199", "discipline": "GP",
                                                       "pct": 10, "effective_from": "2099-01-01"})
    assert nothing.status_code == 404


def test_bulk_increase_versions_every_matching_rate_and_reports_skips():
    _login()
    with SessionLocal() as db:                                   # one undated, one dated, same discipline
        db.add(models.RefRpl(code="9103", discipline="BULKT", rate=100.0))
        db.commit()
    assert _add("9104", 200, "2025-01-01", discipline="BULKT").status_code == 200
    r = client.post("/api/rates/bulk-increase", json={"source": "RPL", "pct": 5, "discipline": "BULKT",
                                                      "effective_from": "2027-01-01"})
    assert r.status_code == 200 and r.json()["increased"] == 2 and r.json()["skipped"] == 0
    rows = {i["code"]: i["rate"] for i in _current("91", on="2027-06-01", discipline="BULKT")["items"]}
    assert rows == {"9103": 105.0, "9104": 210.0}
    rows = {i["code"]: i["rate"] for i in _current("91", on="2026-06-01", discipline="BULKT")["items"]}
    assert rows == {"9103": 100.0, "9104": 200.0}                # history untouched

    again = client.post("/api/rates/bulk-increase", json={"source": "RPL", "pct": 5, "discipline": "BULKT",
                                                          "effective_from": "2027-01-01"})
    assert again.status_code == 409 and "nothing increased" in again.json()["detail"]

    assert _add("9105", 50, "2025-01-01", discipline="BULKT").status_code == 200
    mixed = client.post("/api/rates/bulk-increase", json={"source": "RPL", "pct": 5, "discipline": "BULKT",
                                                          "effective_from": "2027-01-01"}).json()
    assert mixed["increased"] == 1 and mixed["skipped"] == 2 and len(mixed["skipped_detail"]) == 2

    none = client.post("/api/rates/bulk-increase", json={"source": "RPL", "pct": 5, "discipline": "NOBODY",
                                                         "effective_from": "2027-01-01"})
    assert none.status_code == 422
    assert client.post("/api/rates/bulk-increase", json={"source": "SEP", "pct": 5,
                                                         "effective_from": "2027-01-01"}).status_code == 422


# ── adjust / retire ──────────────────────────────────────────────────────────
def test_adjust_corrects_in_place_and_is_logged():
    _login()
    vid = _add("9106", 150, "2025-01-01").json()["id"]
    assert client.post(f"/api/rates/{vid}/adjust", json={"rate": 150}).status_code == 422
    r = client.post(f"/api/rates/{vid}/adjust", json={"rate": 155.5, "note": "capture error"})
    assert r.status_code == 200 and r.json()["rate"] == 155.5 and r.json()["effective_from"] == "2025-01-01"
    lg = client.get("/api/rates/log", params={"code": "9106"}).json()[0]
    assert (lg["action"], lg["old_rate"], lg["new_rate"], lg["note"]) == ("ADJUST", 150.0, 155.5, "capture error")
    with SessionLocal() as db:
        assert db.get(models.RefRpl, ("9106", "GP")).rate == 155.5
    assert client.post("/api/rates/99999999/adjust", json={"rate": 1}).status_code == 404


def test_retire_ends_a_rate_and_the_code_then_has_none():
    _login()
    v1 = _add("9107", 80, "2025-01-01").json()["id"]
    v2 = _add("9107", 90, "2026-01-01").json()["id"]
    assert client.post(f"/api/rates/{v2}/retire", json={"effective_to": "2025-12-31"}).status_code == 422
    assert client.post(f"/api/rates/{v1}/retire", json={"effective_to": "2026-06-30"}).status_code == 422  # overlap
    assert client.post("/api/rates/99999999/retire", json={"effective_to": "2026-06-30"}).status_code == 404
    r = client.post(f"/api/rates/{v2}/retire", json={"effective_to": "2026-06-30"})
    assert r.status_code == 200 and r.json()["effective_to"] == "2026-06-30"
    assert _current("9107", on="2026-06-30")["items"][0]["rate"] == 90.0
    assert _current("9107", on="2026-07-01")["items"][0]["rate"] is None
    with SessionLocal() as db:                                   # retired before today: no undated row
        assert db.get(models.RefRpl, ("9107", "GP")) is None
        book = build_refbook(db, nappi_codes=set())
    assert engine.resolve(book, "TARIFF", "9107", "GP", date(2026, 8, 1)) == (None, "—", None)
    assert engine.resolve(book, "TARIFF", "9107", "GP", date(2026, 3, 1))[0] == 90.0
    lg = client.get("/api/rates/log", params={"code": "9107"}).json()[0]
    assert lg["action"] == "RETIRE" and "open" in lg["note"]


# ── negotiated and NAPPI ─────────────────────────────────────────────────────
def test_negotiated_versions_and_the_undated_editor_steps_aside():
    _login()
    assert _add("9108", 250, "2026-01-01", discipline="", source="NEGOTIATED").status_code == 422   # kind missing
    r = _add("9108", 250, "2026-01-01", discipline="ignored", source="NEGOTIATED", kind="TARIFF")
    assert r.status_code == 200 and r.json()["discipline"] == ""
    assert _current("9108", source="NEGOTIATED")["items"][0]["rate"] == 250.0
    blocked = client.post("/api/admin/negotiated", json={"kind": "TARIFF", "code": "09108", "rate": 1.0})
    assert blocked.status_code == 400 and "dated versions" in blocked.json()["detail"]
    assert client.delete("/api/admin/negotiated/TARIFF/9108").status_code == 400
    with SessionLocal() as db:
        book = build_refbook(db, nappi_codes=set())
    assert engine.resolve(book, "TARIFF", "9108", "GP", date(2026, 2, 1))[1] == "negotiated"
    assert engine.resolve(book, "TARIFF", "9108", "GP", date(2025, 2, 1))[1] != "negotiated"


def test_nappi_exit_price_versions_price_medicines_by_service_date():
    _login()
    assert _add("T9109", 80.0, "2025-01-01", discipline="", source="SEP").json()["kind"] == "NAPPI"
    assert _add("T9109", 88.40, "2026-03-01", discipline="", source="SEP").json()["action"] == "SUPERSEDE"
    listed = _current("T9109", source="SEP")
    assert listed["total"] == 1 and listed["items"][0]["rate"] == 88.40 and listed["items"][0]["versions"] == 2
    with SessionLocal() as db:
        assert db.get(models.RefNappiSep, "T9109").sep == 88.40
        assert build_refbook(db, nappi_codes={"OTHER"}).sep.get("T9109") is None       # only the claim's codes load
    det = client.post("/api/claims", json=_claim(
        "R_RATE_NAPPI", "P_RATE_3", "CAS 9109/02/2026",
        [_line("T9109", 114.92, "2026-02-10", kind="NAPPI"), _line("T9109", 114.92, "2026-03-02", kind="NAPPI")])).json()
    assert det["medical_payable"] == 218.92                      # 104.00 (80 + 30% fee) + 114.92 (88.40 + 30%)
    page = client.get("/api/rates", params={"source": "SEP", "limit": 5}).json()     # SEP pages in SQL
    assert page["total"] >= 2 and len(page["items"]) <= 5


# ── import / export ──────────────────────────────────────────────────────────
def test_csv_import_adds_supersedes_skips_and_reports_bad_rows():
    _login()
    text = ("code,discipline,rate,effective_from,note\n"
            "9110,IMPT,100,2025-01-01,first\n"
            "9110,IMPT,110,2026-01-01,\n"
            "9110,IMPT,110,2026-01-01,\n"          # exact repeat -> skipped
            "9111,,50,2026-01-01,\n"               # RPL needs a discipline
            "9112,IMPT,abc,2026-01-01,\n"          # bad rate
            "9113,IMPT,10,01/02/2026,\n"           # bad date
            "9110,IMPT,90,2025-06-01,\n")          # behind the newest version
    r = client.post("/api/rates/import", json={"csv": text})
    assert r.status_code == 200, r.text
    res = r.json()
    assert (res["added"], res["superseded"], res["skipped"], res["failed"], res["total"]) == (1, 1, 1, 4, 7)
    assert [e.split(":")[0] for e in res["errors"]] == ["row 5", "row 6", "row 7", "row 8"]
    assert _current("9110", on="2025-06-01", discipline="IMPT")["items"][0]["rate"] == 100.0
    assert client.post("/api/rates/import", json={"csv": "code,rate\n1,2"}).status_code == 422

    neg = client.post("/api/rates/import", json={
        "source": "NEGOTIATED", "csv": "kind,code,rate,effective_from\nNAPPI,T9114,12.5,2026-01-01\n"}).json()
    assert neg["added"] == 1


def test_csv_export_round_trips_the_rates_in_force():
    _login()
    out = client.get("/api/rates/export", params={"source": "RPL", "on": "2025-06-01"})
    assert out.status_code == 200 and out.headers["content-type"].startswith("text/csv")
    lines = out.text.strip().split("\n")
    assert lines[0] == "source,kind,code,discipline,rate,effective_from,effective_to"
    assert "RPL,TARIFF,9110,IMPT,100.00,2025-01-01,2025-12-31" in lines
    assert "RPL,TARIFF,190,GP,500.00,," in lines                 # undated seeded rate exports too
    assert not any(line.startswith("RPL,TARIFF,9107,") for line in
                   client.get("/api/rates/export", params={"source": "RPL"}).text.split("\n"))   # retired
    sep = client.get("/api/rates/export", params={"source": "SEP"}).text
    assert "SEP,NAPPI,T9109,,88.40,2026-03-01," in sep and "700101" not in sep   # dated keys only


# ── validation and summary ───────────────────────────────────────────────────
def test_rate_requests_are_validated():
    _login()
    assert _add("9120", 10, "2026-01-01", discipline="").status_code == 422          # RPL needs a discipline
    assert _add("9120", -1, "2026-01-01").status_code == 422
    assert _add("9120", 10, "not-a-date").status_code == 422
    assert _add("9120", 10, "1900-01-01").status_code == 422                         # the baseline sentinel
    assert _add("9120", 10, "2026-01-01", source="BOGUS").status_code == 422
    assert _add("9120", 10, "2026-01-01", source="SEP", kind="TARIFF").status_code == 422
    assert client.post("/api/rates/increase", json={"source": "RPL", "code": "9101", "discipline": "GP",
                                                    "pct": 0, "effective_from": "2099-06-01"}).status_code == 422
    assert client.get("/api/rates", params={"source": "BOGUS"}).status_code == 422
    assert client.get("/api/rates/versions", params={"source": "RPL", "code": "777777", "discipline": "GP"}).json() == []


def test_summary_counts_versions_and_changes():
    _login()
    s = client.get("/api/rates/summary").json()
    assert s["versions"] >= 10 and s["dated_keys"] >= 6 and s["changes"] >= 10
    assert s["by_source"]["SEP"] == 2 and s["by_source"]["NEGOTIATED"] >= 2 and s["last_change"]
    assert len(client.get("/api/rates/log", params={"limit": 3}).json()) == 3
    assert all(r["source"] == "SEP" for r in client.get("/api/rates/log", params={"source": "sep"}).json())


def test_service_helpers_reject_bad_input_directly():
    with SessionLocal() as db:
        for bad in (lambda: svc.make_key("RPL", None, "", "GP"),
                    lambda: svc.make_key("RPL", None, "x" * 33, "GP"),
                    lambda: svc.list_current(db, "nope"),
                    lambda: svc.export_csv(db, "nope"),
                    lambda: svc.increase(db, ADMIN, "RPL", None, "9101", "GP", "abc", "2099-07-01"),
                    lambda: svc.add_or_supersede(db, ADMIN, "RPL", None, "9121", "GP", "abc", "2026-01-01"),
                    lambda: svc.add_or_supersede(db, ADMIN, "RPL", None, "9121", "GP", float("inf"), "2026-01-01")):
            try:
                bad()
            except svc.RateError as e:
                assert e.status == 422
            else:
                raise AssertionError("expected RateError")
        # a key whose only version starts in the future leaves the undated table alone
        svc.add_or_supersede(db, ADMIN, "RPL", None, "9122", "GP", 10, "2099-01-01")
        assert db.get(models.RefRpl, ("9122", "GP")) is None
        assert svc.list_current(db, "RPL", q="9122")["items"][0]["rate"] is None
