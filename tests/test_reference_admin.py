"""Reference data an administrator maintains on screen: diagnosis codes, the tariff codes
excluded from flat-rate pricing, and the code crosswalk."""
from __future__ import annotations

import test_api  # noqa: F401  (sets RIE_DATABASE_URL + imports the app + seeds)
from fastapi.testclient import TestClient
from sqlalchemy import select

from engine import resolve
from server import crosswalk as xw
from server import models
from server.db import SessionLocal
from server.main import app
from server.reference_data import build_refbook

client = TestClient(app)
A = "/api/admin"


def _login(user="admin"):
    assert client.post("/api/auth/login", json={"username": user, "password": user}).status_code == 200


def _price(code, discipline="GP"):
    with SessionLocal() as db:
        return resolve(build_refbook(db, nappi_codes=set()), "TARIFF", code, discipline)


def _rate(code, rate, discipline="GP"):
    with SessionLocal() as db:
        db.merge(models.RefRpl(code=code, discipline=discipline, rate=rate))
        db.commit()


def _audit_actions(area):
    rows = client.get(f"{A}/audit/search", params={"area": area, "limit": 50}).json()["rows"]
    return [(r["action"], r["target"]) for r in rows]


def test_only_an_administrator_reaches_these_pages():
    _login("handler")
    for path in ("icd10", "icd10/summary", "exclusions", "crosswalk"):
        assert client.get(f"{A}/{path}").status_code == 403, path
    assert client.post(f"{A}/icd10", json={"code": "S72.00", "description": "x"}).status_code == 403
    assert client.post(f"{A}/exclusions", json={"code": "1", "reason": "x"}).status_code == 403
    assert client.post(f"{A}/crosswalk", json={"code": "1", "target_code": "2"}).status_code == 403
    # the lookup stays open to every signed-in operator
    assert client.get("/api/reference/icd10", params={"q": "S72"}).status_code == 200


# ── diagnosis codes ──────────────────────────────────────────────────────────
def test_a_diagnosis_code_is_added_corrected_withdrawn_and_removed():
    _login()
    r = client.post(f"{A}/icd10", json={"code": "s99.91", "description": "Test injury of ankle"})
    assert r.status_code == 200
    assert r.json() == {"code": "S99.91", "description": "Test injury of ankle", "code3_desc": "",
                        "chapter_desc": "", "valid_primary": True, "valid_clinical": True}
    # correct the wording, keep the rest
    r = client.post(f"{A}/icd10", json={"code": "S99.91", "description": "Test injury of the ankle"}).json()
    assert r["description"] == "Test injury of the ankle" and r["valid_primary"] is True
    # withdraw from use: neither a primary nor a clinical code any more
    r = client.post(f"{A}/icd10", json={"code": "S99.91", "valid_primary": False, "valid_clinical": False}).json()
    assert (r["valid_primary"], r["valid_clinical"]) == (False, False)
    assert client.get(f"{A}/icd10", params={"q": "S99.91", "use": "heading"}).json()["total"] == 1
    assert client.get(f"{A}/icd10", params={"q": "S99.91", "use": "clinical"}).json()["total"] == 0
    assert client.get("/api/reference/icd10", params={"code": "S99.91"}).json()[0]["description"] == "Test injury of the ankle"
    assert client.request("DELETE", f"{A}/icd10/S99.91").json() == {"removed": "S99.91"}
    assert client.request("DELETE", f"{A}/icd10/S99.91").status_code == 400
    assert [a for a, t in _audit_actions("icd10") if t == "S99.91"] == [
        "icd10.remove", "icd10.update", "icd10.update", "icd10.add"]


def test_a_diagnosis_code_must_be_well_formed():
    _login()
    for body in ({"code": "72.00", "description": "no letter"},
                 {"code": "S7", "description": "too short"},
                 {"code": "S72.00", "description": "  "},
                 {"code": "S72 00", "description": "space"}):
        assert client.post(f"{A}/icd10", json=body).status_code == 400, body
    # a morphology code with a slash is a real ICD-10 form
    assert client.post(f"{A}/icd10", json={"code": "M9999/9", "description": "Test morphology"}).status_code == 200
    assert client.request("DELETE", f"{A}/icd10/M9999/9").json() == {"removed": "M9999/9"}
    bad = client.post(f"{A}/icd10", json={"code": "S98.99", "description": "x",
                                          "valid_primary": True, "valid_clinical": False})
    assert bad.status_code == 400 and "primary" in bad.json()["detail"]


ICD_CSV = """code,description,valid_primary,valid_clinical,chapter_desc
T90.01,Test sequela one,yes,yes,Test chapter
T90.02,Test sequela two,no,yes,Test chapter
T90,Test heading,no,no,Test chapter
bad,Not a code,yes,yes,
T90.03,,yes,yes,
T90.01,Twice in the file,yes,yes,
T90.04,Primary but not clinical,yes,no,
"""


def test_an_edition_of_diagnosis_codes_loads_from_a_file():
    _login()
    r = client.post(f"{A}/icd10/import", json={"csv": ICD_CSV, "edition": "Test MIT 2027"}).json()
    assert (r["added"], r["updated"], r["unchanged"], r["failed"]) == (3, 0, 0, 4)
    assert [e.split(":")[0] for e in r["errors"]] == ["row 5", "row 6", "row 7", "row 8"]
    assert client.get(f"{A}/icd10", params={"q": "T90", "use": "heading"}).json()["total"] == 1
    summary = client.get(f"{A}/icd10/summary").json()
    assert summary["edition"] == "Test MIT 2027" and summary["edition_loaded_at"]
    ed = {e["kind"]: e for e in client.get("/api/reference/editions").json()}["icd10"]
    assert ed["version"] == "Test MIT 2027" and ed["n"] == summary["total"]
    # loading it again changes nothing; a corrected description updates that one code
    again = client.post(f"{A}/icd10/import", json={"csv": ICD_CSV}).json()
    assert (again["added"], again["updated"], again["unchanged"]) == (0, 0, 3)
    fixed = client.post(f"{A}/icd10/import",
                        json={"csv": "code,description\nT90.02,Test sequela two (corrected)\n"}).json()
    assert (fixed["added"], fixed["updated"]) == (0, 1)
    row = client.get(f"{A}/icd10", params={"q": "T90.02"}).json()["rows"][0]
    assert row["description"] == "Test sequela two (corrected)" and row["valid_primary"] is False
    assert client.post(f"{A}/icd10/import", json={"csv": "code,name\nT90.05,x\n"}).status_code == 400
    for code in ("T90.01", "T90.02", "T90"):
        client.request("DELETE", f"{A}/icd10/{code}")


# ── flat-rate exclusions ─────────────────────────────────────────────────────
def test_an_excluded_code_is_not_priced_and_removing_it_prices_it_again():
    _login()
    _rate("94001", 250.0)
    assert _price("94001")[0] == 250.0
    assert client.post(f"{A}/exclusions", json={"code": "94001", "reason": " "}).status_code == 400
    r = client.post(f"{A}/exclusions", json={"code": "094001", "reason": "cost of material"}).json()
    assert (r["code"], r["reason"], r["origin"], r["created_by"], r["has_rate"]) == (
        "094001", "cost of material", "manual", "admin", True)
    assert _price("94001") == (None, "—", None)                 # excluded: no reference rate
    # the same code written another way is the same code
    assert client.post(f"{A}/exclusions", json={"code": "94001", "reason": "again"}).status_code == 400
    assert any(x["code"] == "094001" for x in client.get(f"{A}/exclusions").json())
    out = client.post(f"{A}/exclusions/remove", json={"code": "094001", "reason": "priced after all"})
    assert out.json() == {"removed": "094001"}
    assert _price("94001")[0] == 250.0
    assert client.post(f"{A}/exclusions/remove", json={"code": "094001"}).status_code == 400
    assert [a for a, t in _audit_actions("non_bench") if t == "094001"] == ["non_bench.remove", "non_bench.add"]


# ── code crosswalk ───────────────────────────────────────────────────────────
def test_a_new_database_starts_from_the_built_in_crosswalk():
    _login()
    rows = {r["code"]: r for r in client.get(f"{A}/crosswalk").json()}
    built_in = {e.coida.lstrip("0") or "0": e for e in xw.CROSSWALK}
    assert set(built_in) <= set(rows)
    assert all(rows[c]["status"] == e.status and rows[c]["target_code"] == e.raf
               for c, e in built_in.items())
    assert rows["190"]["billed_as"] == "0190" and rows["190"]["origin"] == "seed"


def test_a_match_changes_pricing_only_once_it_is_signed_off():
    _login()
    _rate("95002", 400.0)
    r = client.post(f"{A}/crosswalk", json={"code": "095001", "target_code": "95002",
                                           "family": "test", "description": "Test visit"}).json()
    assert (r["code"], r["billed_as"], r["status"], r["effect"]) == ("95001", "095001", "PROPOSED", "NOT_SIGNED_OFF")
    assert r["target_rates"] == [{"discipline": "GP", "rate": 400.0}]
    assert _price("95001")[0] is None                            # proposed: prices nothing
    url = f"{A}/crosswalk/status"
    assert client.post(url, json={"code": "95001", "status": "CONFIRMED", "reason": ""}).status_code == 400
    ok = client.post(url, json={"code": "95001", "status": "CONFIRMED",
                                "reason": "Dr A Example, tariff committee, 11 Nov 2026"}).json()
    assert (ok["status"], ok["effect"], ok["confirmed_by"]) == ("CONFIRMED", "IN_USE", "admin")
    assert "tariff committee" in ok["evidence"]
    rate, source, standing = _price("95001")
    assert (rate, standing.name) == (400.0, "ACCEPTED")
    # withdrawing the sign-off stops it at once
    back = client.post(url, json={"code": "95001", "status": "PROPOSED", "reason": "under review"}).json()
    assert (back["status"], back["confirmed_by"]) == ("PROPOSED", "")
    assert _price("95001")[0] is None
    assert client.post(f"{A}/crosswalk/remove", json={"code": "95001"}).json() == {"removed": "95001"}
    assert [a for a, t in _audit_actions("crosswalk") if t == "95001"] == [
        "crosswalk.remove", "crosswalk.status", "crosswalk.status", "crosswalk.add"]


def test_changing_the_target_of_a_signed_off_match_needs_a_new_sign_off():
    _login()
    _rate("95012", 300.0)
    _rate("95013", 900.0)
    client.post(f"{A}/crosswalk", json={"code": "95011", "target_code": "95012"})
    client.post(f"{A}/crosswalk/status", json={"code": "95011", "status": "CONFIRMED", "reason": "signed"})
    assert _price("95011")[0] == 300.0
    r = client.post(f"{A}/crosswalk", json={"code": "95011", "target_code": "95013"}).json()
    assert (r["status"], r["confirmed_by"], r["target_code"]) == ("PROPOSED", "", "95013")
    assert _price("95011")[0] is None                            # not paid at the dearer code unasked
    # a wording change alone keeps the sign-off
    client.post(f"{A}/crosswalk/status", json={"code": "95011", "status": "CONFIRMED", "reason": "signed again"})
    r = client.post(f"{A}/crosswalk", json={"code": "95011", "target_code": "95013", "description": "Reworded"}).json()
    assert r["status"] == "CONFIRMED" and _price("95011")[0] == 900.0
    client.post(f"{A}/crosswalk/remove", json={"code": "95011"})


def test_the_page_says_when_a_signed_off_match_does_nothing():
    _login()
    _rate("95021", 100.0)
    _rate("95022", 200.0)
    # the billed code has a rate of its own, which wins
    client.post(f"{A}/crosswalk", json={"code": "95021", "target_code": "95022"})
    r = client.post(f"{A}/crosswalk/status", json={"code": "95021", "status": "CONFIRMED", "reason": "x"}).json()
    assert (r["effect"], r["own_rate"]) == ("OWN_RATE", True) and _price("95021")[0] == 100.0
    # the target has no rate loaded
    client.post(f"{A}/crosswalk", json={"code": "95023", "target_code": "95099"})
    r = client.post(f"{A}/crosswalk/status", json={"code": "95023", "status": "CONFIRMED", "reason": "x"}).json()
    assert (r["effect"], r["target_rates"]) == ("TARGET_UNPRICED", []) and _price("95023")[0] is None
    for code in ("95021", "95023"):
        client.post(f"{A}/crosswalk/remove", json={"code": code})


def test_crosswalk_entries_without_a_target():
    _login()
    r = client.post(f"{A}/crosswalk", json={"code": "95031", "description": "No match found yet"}).json()
    assert (r["status"], r["target_code"]) == ("NEEDS_SME", None)
    url = f"{A}/crosswalk/status"
    assert client.post(url, json={"code": "95031", "status": "CONFIRMED", "reason": "x"}).status_code == 400
    none = client.post(url, json={"code": "95031", "status": "NO_RAF_EQUIVALENT", "reason": "not in the list"}).json()
    assert none["status"] == "NO_RAF_EQUIVALENT" and none["target_code"] is None
    assert client.post(f"{A}/crosswalk", json={"code": "95031", "target_code": "95031"}).status_code == 400
    assert client.post(url, json={"code": "95999", "status": "PROPOSED"}).status_code == 400
    client.post(f"{A}/crosswalk/remove", json={"code": "95031"})


def test_an_emptied_crosswalk_is_not_refilled():
    from server.reference_admin_service import seed_crosswalk
    _login()
    with SessionLocal() as db:
        saved = [{c.name: getattr(r, c.name) for c in models.RefCrosswalk.__table__.columns}
                 for r in db.scalars(select(models.RefCrosswalk))]
    try:
        for row in saved:
            client.post(f"{A}/crosswalk/remove", json={"code": row["code"]})
        assert client.get(f"{A}/crosswalk").json() == []
        with SessionLocal() as db:
            seed_crosswalk(db)                                   # what start-up runs
            db.commit()
        assert client.get(f"{A}/crosswalk").json() == []         # the administrator's change stands
    finally:
        with SessionLocal() as db:
            for row in saved:
                db.merge(models.RefCrosswalk(**row))
            db.commit()
