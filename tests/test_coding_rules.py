"""Coding rules and billing signals (port of CIE's coding rules and scorer signals).

A coding rule is the tariff's own billing rule for a code, held as reference data: a
once-per-encounter limit, a time-modifier ladder, or a percentage-of-time modifier. The billing
signals are encounter-shaped screens fed by the corpus. These tests use their own tariff codes
(92xx), providers and parties so the shared seeded reference is never disturbed."""
from __future__ import annotations

import sqlite3
import sys
from datetime import date
from pathlib import Path

import test_api  # noqa: F401  (sets RIE_DATABASE_URL + imports the app first)
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

import engine
from server import coding_service, models
from server.db import SessionLocal
from server.main import app
from server.pipeline_service import billing_activity, prior_lines
from server.reference_data import build_refbook

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "db"))
import load_reference  # noqa: E402

client = TestClient(app)
RATES = {"9201": 280.0, "9202": 400.0, "9203": 300.0, "9205": 100.0, "9206": 500.0}


def _login(user="admin"):
    assert client.post("/api/auth/login", json={"username": user, "password": user}).status_code == 200


def _seed_rates():
    with SessionLocal() as db:
        for code, rate in RATES.items():
            if db.get(models.RefRpl, (code, "GP")) is None:
                db.add(models.RefRpl(code=code, discipline="GP", rate=rate))
        db.commit()


def _rule(code, rule, param=0.0, basis=""):
    return client.post("/api/admin/code-rules",
                       json={"code": code, "rule": rule, "param": param, "basis": basis})


def _claim(cid, party, cas, lines, accident="2026-02-01", **kw):
    return {"claim_id": cid, "claim_type": "SUPPLIER", "party_token": party,
            "accident_date": accident, "lodged_on": "2026-03-01", "case_number_raw": cas,
            "today": "2026-07-05", "payee_verified": True,
            "documents": {"RAF2": True, "OAR": True, "INVOICES": True, "BANK": True},
            "lines": lines, **kw}


def _line(code, amount, svc="2026-03-02", qty=1, provider="PR_CR", **kw):
    return {"kind": "TARIFF", "code": code, "qty": qty, "amount": amount, "service_date": svc,
            "provider_id": provider, "dx": "S72", **kw}


def _submit(*args, **kw):
    r = client.post("/api/claims", json=_claim(*args, **kw))
    assert r.status_code == 200, r.text
    return r.json()


def _stored(cid):
    with SessionLocal() as db:
        return [(r.code, r.reference, r.payable, r.reasons) for r in db.scalars(
            select(models.BillingLineRecord).where(models.BillingLineRecord.claim_id == cid)
            .order_by(models.BillingLineRecord.id))]


# ── maintenance ──────────────────────────────────────────────────────────────
def test_code_rules_are_admin_only():
    assert TestClient(app).get("/api/admin/code-rules").status_code == 401
    _login("handler")
    assert client.get("/api/admin/code-rules").status_code == 403
    assert _rule("9201", "ONCE_PER_ENCOUNTER").status_code == 403
    assert client.delete("/api/admin/code-rules/9201").status_code == 403


def test_add_replace_and_remove_a_rule():
    _login()
    r = _rule("09290", "ONCE_PER_ENCOUNTER", param=7, basis="tariff description: use once only")
    assert r.status_code == 200
    assert r.json() == {"code": "9290", "rule": "ONCE_PER_ENCOUNTER", "param": 0.0,      # no parameter kept
                        "basis": "tariff description: use once only", "origin": "manual"}
    assert _rule("9290", "TIME_BLOCK", param=30).json()["rule"] == "TIME_BLOCK"         # one rule per code
    rows = [x for x in client.get("/api/admin/code-rules").json() if x["code"] == "9290"]
    assert len(rows) == 1 and rows[0]["param"] == 30.0
    with SessionLocal() as db:
        assert build_refbook(db, nappi_codes=set()).code_rules["9290"] == ("TIME_BLOCK", 30.0)
        actions = [a.action for a in db.scalars(select(models.AdminAudit)
                                                .where(models.AdminAudit.target == "9290"))]
    assert actions == ["code_rule.upsert", "code_rule.upsert"]
    assert client.delete("/api/admin/code-rules/09290").json() == {"ok": True}
    assert client.delete("/api/admin/code-rules/9290").status_code == 400               # already gone


def test_rule_validation():
    _login()
    assert "code is required" in _rule(" ", "ONCE_PER_ENCOUNTER").json()["detail"]
    assert "rule must be one of" in _rule("9291", "SOMETIMES").json()["detail"]
    assert "block length" in _rule("9291", "TIME_BLOCK").json()["detail"]
    assert "block length" in _rule("9291", "TIME_BLOCK", param=5000).json()["detail"]
    assert "share" in _rule("9291", "PCT_OF_TIME", param=2).json()["detail"]
    assert "param must be a number" in _rule("9291", "PCT_OF_TIME", param="half").json()["detail"]
    assert all(x["code"] != "9291" for x in client.get("/api/admin/code-rules").json())


# ── the rules at adjudication ────────────────────────────────────────────────
def test_once_only_code_is_paid_once_per_encounter_across_claims():
    _login()
    _seed_rates()
    assert _rule("9201", "ONCE_PER_ENCOUNTER").status_code == 200
    first = _submit("R_CR_ONCE_1", "P_CR_1", "CAS 9201/02/2026", [_line("9201", 280.0)])
    assert first["medical_payable"] == 280.0 and first["reasons"] == []

    # the same claimant, provider and day on a second claim, at a different amount
    again = _submit("R_CR_ONCE_2", "P_CR_1", "CAS 9201/02/2026", [_line("9201", 250.0)])
    assert again["medical_payable"] == 0.0 and again["reasons"] == ["UNBUNDLING_CONFLICT"]
    assert again["disposition"] == "ADJUSTED"
    assert _stored("R_CR_ONCE_2") == [("9201", 280.0, 0.0, ["UNBUNDLING_CONFLICT"])]   # reference kept, nothing paid

    # another day, and another claimant, are other encounters
    other_day = _submit("R_CR_ONCE_3", "P_CR_1", "CAS 9201/02/2026", [_line("9201", 250.0, svc="2026-03-03")])
    other_party = _submit("R_CR_ONCE_4", "P_CR_2", "CAS 9202/02/2026", [_line("9201", 250.0)])
    assert other_day["medical_payable"] == other_party["medical_payable"] == 250.0

    with SessionLocal() as db:                                   # the ledger carries the encounter key
        book = build_refbook(db, nappi_codes=set())
        probe = engine.Claim("R_PROBE", "SUPPLIER", "P_CR_1", date(2026, 2, 1), date(2026, 3, 1),
                             None, {}, [])
        assert ("ONCE", "P_CR_1", "PR_CR", date(2026, 3, 2), "9201") in prior_lines(db, probe, book)
        assert not any(k[0] == "ONCE" for k in prior_lines(db, probe))       # no book -> line keys only


def test_time_modifier_is_priced_by_its_ladder_not_per_minute():
    _login()
    _seed_rates()
    assert _rule("9202", "TIME_BLOCK", param=30).status_code == 200
    det = _submit("R_CR_TIME_1", "P_CR_3", "CAS 9203/02/2026", [_line("9202", 1000.0, qty=45)])
    assert det["medical_payable"] == 800.0 and det["reasons"] == ["BILLED_OVER_REFERENCE"]
    assert _stored("R_CR_TIME_1") == [("9202", 800.0, 800.0, ["BILLED_OVER_REFERENCE"])]


def test_percentage_of_time_modifier_follows_the_time_line():
    _login()
    _seed_rates()
    assert _rule("9203", "TIME_ANAES").status_code == 200
    assert _rule("9204", "PCT_OF_TIME", param=0.5).status_code == 200
    det = _submit("R_CR_PCT_1", "P_CR_4", "CAS 9204/02/2026",
                  [_line("9203", 1650.0, qty=75), _line("9204", 900.0)])
    assert det["medical_payable"] == 2475.0                       # 1,650 + 50% of it
    assert [x[1] for x in _stored("R_CR_PCT_1")] == [1650.0, 825.0]

    alone = _submit("R_CR_PCT_2", "P_CR_5", "CAS 9205/02/2026", [_line("9204", 900.0)])
    assert alone["reasons"] == ["REFERENCE_UNRESOLVED"] and alone["needs_review"] is True
    assert _stored("R_CR_PCT_2")[0][1] is None


# ── billing signals ──────────────────────────────────────────────────────────
def test_provider_billing_thirty_claimants_in_one_day_is_flagged():
    _login()
    _seed_rates()
    for i in range(29):
        det = _submit(f"R_CR_DAY_{i}", f"P_CR_DAY_{i}", f"CAS {9300 + i}/02/2026",
                      [_line("9206", 500.0, provider="PR_CR_DAY")])
        assert "IMPOSSIBLE_DAY" not in det["reasons"]
    hit = _submit("R_CR_DAY_29", "P_CR_DAY_29", "CAS 9329/02/2026",
                  [_line("9206", 500.0, provider="PR_CR_DAY")])
    assert hit["reasons"] == ["IMPOSSIBLE_DAY"] and hit["band"] == "AMBER"
    assert hit["disposition"] == "FRAUD" and hit["eligible_to_pay"] is False

    # the same volume on a hospital account is ordinary
    hosp = _submit("R_CR_DAY_30", "P_CR_DAY_30", "CAS 9330/02/2026",
                   [_line("9206", 500.0, provider="PR_CR_DAY")], facility=True)
    assert hosp["reasons"] == [] and hosp["disposition"] == "CLEAN"


def test_eight_encounters_for_one_claimant_in_a_week_is_flagged():
    _login()
    _seed_rates()
    # 2-8 March 2026 is one ISO week; a visit a day for seven days, then a second provider
    for i, day in enumerate(range(2, 9)):
        det = _submit(f"R_CR_WK_{i}", "P_CR_WK", "CAS 9340/02/2026",
                      [_line("9206", 500.0, svc=f"2026-03-0{day}", provider="PR_CR_WK")])
        assert "IMPOSSIBLE_WEEK" not in det["reasons"]
    eighth = _submit("R_CR_WK_7", "P_CR_WK", "CAS 9340/02/2026",
                     [_line("9206", 500.0, svc="2026-03-08", provider="PR_CR_WK2")])
    assert eighth["reasons"] == ["IMPOSSIBLE_WEEK"]
    assert eighth["band"] == "GREEN" and eighth["disposition"] == "CLEAN"    # visible, never alone dispositive


def test_three_same_discipline_providers_is_recorded_in_shadow():
    _login()
    _seed_rates()
    for i, (prov, disc) in enumerate((("PR_CR_S1", ""), ("PR_CR_S2", "GP"), ("PR_CR_PT", "Physiotherapy"))):
        det = _submit(f"R_CR_SHOP_{i}", "P_CR_SHOP", "CAS 9350/02/2026",
                      [_line("9206", 500.0, svc=f"2026-03-1{i}", provider=prov, discipline=disc)])
        assert "PROVIDER_SHOPPING" not in det["shadow_signals"]
    third = _submit("R_CR_SHOP_3", "P_CR_SHOP", "CAS 9350/02/2026",
                    [_line("9206", 500.0, svc="2026-03-16", provider="PR_CR_S3")])
    assert third["shadow_signals"][0] == "PROVIDER_SHOPPING" and third["reasons"] == []
    assert third["disposition"] == "CLEAN"                                   # shadow: computed, not shown, no points


def test_billing_activity_reads_other_claims_only():
    _login()
    _seed_rates()
    _submit("R_CR_ACT_1", "P_CR_ACT", "CAS 9360/02/2026",
            [_line("9206", 500.0, svc="2026-03-10", provider="PR_CR_A1", discipline="Physiotherapy")])
    _submit("R_CR_ACT_2", "P_CR_ACT", "CAS 9360/02/2026",
            [_line("9206", 500.0, svc="2026-03-11", provider="PR_CR_HOSP")], facility=True)
    _submit("R_CR_ACT_3", "P_CR_OTHER", "CAS 9361/02/2026",
            [_line("9206", 500.0, svc="2026-03-10", provider="PR_CR_A1")])
    probe = engine.Claim("R_CR_ACT_1", "SUPPLIER", "P_CR_ACT", date(2026, 2, 1), date(2026, 3, 1), None, {},
                         [engine.Line("TARIFF", "9206", 1.0, 500.0, date(2026, 3, 10), "PR_CR_A1", "S72")])
    with SessionLocal() as db:
        act = billing_activity(db, probe)
        empty = billing_activity(db, engine.Claim("R_X", "SUPPLIER", "P_CR_ACT", date(2026, 2, 1),
                                                  date(2026, 3, 1), None, {}, []))
    assert act.provider_day == {("PR_CR_A1", date(2026, 3, 10)): 1}          # the other claimant, not this one
    assert act.claimant_encounters == set()                                  # the hospital claim adds none
    assert act.claimant_providers == {"GP": {"PR_CR_HOSP"}}                  # this claim itself is excluded
    assert empty == engine.Activity()


def test_facility_flag_is_a_strict_boolean():
    _login()
    r = client.post("/api/claims", json=_claim("R_CR_BAD", "P_CR_9", "CAS 9370/02/2026",
                                               [_line("9206", 500.0)], facility="yes"))
    assert r.status_code == 422


# ── the reference loader ─────────────────────────────────────────────────────
def test_loader_reads_once_only_codes_from_the_tariff_and_keeps_manual_rules(tmp_path):
    ref = tmp_path / "reference.db"
    con = sqlite3.connect(ref)
    con.execute("CREATE TABLE ref_tariffs (tariff_code TEXT, norm_code TEXT, description TEXT, "
                "rate REAL, discipline TEXT, year INTEGER)")
    con.executemany("INSERT INTO ref_tariffs VALUES (?,?,?,?,?,2026)", [
        ("9280", "9280", "Preparation of equipment. Use once only per encounter", 100.0, "GP"),
        ("9280", "9280", "Preparation of equipment. Use once only per encounter", 120.0, "Dental"),
        ("9281", "9281", "Dressing, once per week", 50.0, "GP"),               # not a per-encounter limit
        ("9282", "9282", "Bone densitometry (to be charged once only)", 70.0, "GP"),
        ("0011", "11", "Emergency theatre time, per half-hour", 419.28, "GP"),
        ("0018", "18", "Modifier", 489.81, "GP"),
        ("9283", None, "no code", 1.0, "GP"),
    ])
    con.commit()
    con.row_factory = sqlite3.Row
    _login()
    assert _rule("9282", "TIME_BLOCK", param=15, basis="set by hand").status_code == 200
    try:
        with SessionLocal() as db:
            n = load_reference._load_code_rules(db, con)
            db.commit()
            got = {r.code: (r.rule, r.param, r.origin) for r in db.scalars(
                select(models.RefCodeRule).where(models.RefCodeRule.code.in_(["9280", "9281", "9282", "11", "18"])))}
            basis = db.get(models.RefCodeRule, "9280").basis
        assert n == 3
        assert got == {"9280": ("ONCE_PER_ENCOUNTER", 0.0, "tariff"),
                       "9282": ("TIME_BLOCK", 15.0, "manual"),                 # the hand-set rule wins
                       "11": ("TIME_BLOCK", 30.0, "standard"),
                       "18": ("PCT_OF_TIME", 0.5, "standard")}
        assert basis == "tariff description: “Use once only”"
        with SessionLocal() as db:                                             # a reload replaces, never doubles
            assert load_reference._load_code_rules(db, con) == 3
            db.commit()
    finally:
        con.close()
        with SessionLocal() as db:                                             # leave the shared reference as found
            db.execute(delete(models.RefCodeRule).where(
                models.RefCodeRule.code.in_(["9280", "9282", "11", "18"])))
            db.commit()


def test_loader_with_no_rules_in_the_tariff_loads_none(tmp_path):
    con = sqlite3.connect(tmp_path / "reference.db")
    con.execute("CREATE TABLE ref_tariffs (tariff_code TEXT, norm_code TEXT, description TEXT, "
                "rate REAL, discipline TEXT, year INTEGER)")
    con.row_factory = sqlite3.Row
    try:
        with SessionLocal() as db:
            assert load_reference._load_code_rules(db, con) == 0
            db.commit()
    finally:
        con.close()


# ── price drift ──────────────────────────────────────────────────────────────
def test_price_drift_ranks_a_provider_whose_billing_ratchets_up():
    _login()
    _seed_rates()
    for m in range(6):                                  # March..August 2026; billed 100%..125% of reference
        for prov, factor in (("PR_CR_UP", 1 + 0.05 * m), ("PR_CR_FLAT", 1.0)):
            lines = [_line("9205", round(100.0 * factor, 2), svc=f"2026-{3 + m:02d}-{10 + d}", provider=prov)
                     for d in range(5)]
            _submit(f"R_CR_DRIFT_{prov}_{m}", f"P_CR_DRIFT_{prov}_{m}", f"CAS {9400 + m}/02/2026", lines)
    rep = client.get("/api/coding/drift").json()
    assert rep["min_months"] == 6 and rep["min_lines"] == 5
    rising = {r["provider_id"]: r for r in rep["rising"]}
    assert "PR_CR_FLAT" not in rising                    # flat billing is not drift
    up = rising["PR_CR_UP"]
    assert up["n_months"] == 6 and (up["first_month"], up["last_month"]) == ("2026-03", "2026-08")
    assert (up["first_ratio"], up["last_ratio"]) == (1.0, 1.25) and up["slope_per_month"] == 0.05
    assert [s["lines"] for s in up["series"]] == [5] * 6

    assert client.get("/api/coding/drift", params={"min_months": 7}).json()["rising"] == []
    assert client.get("/api/coding/drift", params={"min_lines": 6}).json()["n_providers"] == 0
    assert client.get("/api/coding/drift", params={"min_months": 1}).status_code == 422


def test_drift_slope_needs_two_distinct_points():
    assert coding_service._ols_slope([]) is None
    assert coding_service._ols_slope([(0.0, 1.0)]) is None
    assert coding_service._ols_slope([(0.0, 1.0), (1.0, 1.5), (2.0, 2.0)]) == 0.5
