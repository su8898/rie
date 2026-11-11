"""Price lists — whole tariff editions an administrator creates and maintains.

Covers who may do what, the draft / published / retired lifecycle, loading entries by file, the
change of a list's legal standing, and the rule that holding a list prices nothing.
"""
from __future__ import annotations

from pathlib import Path

import test_api  # noqa: F401  (sets RIE_DATABASE_URL + imports the app + seeds)
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from server import models
from server.db import SessionLocal
from server.main import app

client = TestClient(app)
BASE = "/api/price-lists"
EXTRACT = Path(__file__).resolve().parent.parent / "db" / "raf_tariff" / "raf_tariff_2021_22_prices.csv"


def _login(user="admin"):
    assert client.post("/api/auth/login", json={"username": user, "password": user}).status_code == 200


def _new(name, **kw):
    body = {"name": name, "edition": "2026", "source": "Test Gazette No. 1",
            "effective_from": "2026-04-01", **kw}
    r = client.post(BASE, json=body)
    assert r.status_code == 200, r.text
    return r.json()


def _entry(list_id, **kw):
    body = {"discipline": "Physiotherapy", "code": "301", "description": "Consultation",
            "value_rand": 250.0, **kw}
    r = client.post(f"{BASE}/{list_id}/entries", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def _rows(list_id, **params):
    return client.get(f"{BASE}/{list_id}/entries", params={"limit": 200, **params}).json()


# ── who may do what ──────────────────────────────────────────────────────────
def test_anyone_signed_in_can_browse_but_only_an_administrator_can_change():
    _login("admin")
    pl = _new("Access list")
    _entry(pl["id"])
    client.post("/api/auth/logout")
    assert client.get(BASE).status_code == 401
    _login("handler")
    assert any(x["name"] == "Access list" for x in client.get(BASE).json())
    assert client.get(f"{BASE}/{pl['id']}").json()["counts"]["entries"] == 1
    assert _rows(pl["id"])["total"] == 1
    assert client.get(f"{BASE}/{pl['id']}/export").status_code == 200
    for method, path, body in (
            ("post", BASE, {"name": "x"}),
            ("patch", f"{BASE}/{pl['id']}", {"notes": "x"}),
            ("post", f"{BASE}/{pl['id']}/entries", {"code": "1", "value_rand": 1}),
            ("post", f"{BASE}/{pl['id']}/import", {"csv": "code,value_rand\n1,2\n"}),
            ("post", f"{BASE}/{pl['id']}/publish", None),
            ("post", f"{BASE}/{pl['id']}/legal-status",
             {"legal_status": "INTERDICTED", "reason": "x"}),
            ("delete", f"{BASE}/{pl['id']}", None)):
        r = getattr(client, method)(path, json=body) if body is not None else getattr(client, method)(path)
        assert r.status_code == 403, (method, path, r.status_code)


# ── creating and editing a draft ─────────────────────────────────────────────
def test_a_new_list_is_a_draft_and_names_are_unique():
    _login()
    pl = _new("Draft rules list", legal_status="INTERDICTED", status_note="Set aside by a court")
    assert pl["state"] == "DRAFT" and pl["legal_status"] == "INTERDICTED"
    assert pl["created_by"] == "admin" and pl["counts"]["entries"] == 0
    assert client.post(BASE, json={"name": "draft RULES list"}).status_code == 409
    assert client.post(BASE, json={"name": "  "}).status_code in (409, 422)
    assert client.post(BASE, json={"name": "Bad standing", "legal_status": "ENDOGENOUS"}).status_code == 422
    r = client.post(BASE, json={"name": "Backwards", "effective_from": "2026-05-01",
                                "effective_to": "2026-04-01"})
    assert r.status_code == 422 and "before" in r.json()["detail"]


def test_entries_are_added_edited_and_removed_in_a_draft():
    _login()
    pl = _new("Entry list")
    e = _entry(pl["id"], code="0190", price_column="specialist", units=15, value_rand=None,
               description="Consultation")
    assert (e["code"], e["units"], e["value_rand"], e["price_column"]) == ("0190", 15.0, None, "specialist")
    _entry(pl["id"], code="0190", price_column="general_practitioner", units=15, value_rand=None)
    r = client.patch(f"{BASE}/{pl['id']}/entries/{e['id']}", json={"units": 18, "note": "corrected"})
    assert r.json()["units"] == 18.0 and r.json()["code"] == "0190"
    # an entry needs something to identify it, and figures cannot be negative
    assert client.post(f"{BASE}/{pl['id']}/entries", json={"value_rand": 5}).status_code == 422
    assert client.post(f"{BASE}/{pl['id']}/entries", json={"code": "1", "value_rand": -5}).status_code == 422
    # a priced line with no code is allowed: tariffs print them
    assert _entry(pl["id"], code="", description="Flying time, 30 minutes", value_rand=16777.21)["code"] == ""
    assert client.delete(f"{BASE}/{pl['id']}/entries/{e['id']}").json() == {"deleted": e["id"]}
    assert client.delete(f"{BASE}/{pl['id']}/entries/{e['id']}").status_code == 404
    got = client.get(f"{BASE}/{pl['id']}").json()
    assert got["counts"]["entries"] == 2 and got["counts"]["units_only"] == 1
    assert got["columns"] == ["general_practitioner", "standard"]


def test_conversion_factors_are_recorded_with_the_list():
    _login()
    pl = _new("Factor list")
    r = client.put(f"{BASE}/{pl['id']}/factors", json={"factors": [
        {"name": "consultation", "value": 33.69}, {"name": "procedural", "value": 16.05}]})
    assert r.json()["factors"] == [{"name": "consultation", "value": 33.69},
                                   {"name": "procedural", "value": 16.05}]
    twice = client.put(f"{BASE}/{pl['id']}/factors", json={"factors": [
        {"name": "a", "value": 1}, {"name": "A", "value": 2}]})
    assert twice.status_code == 422


# ── loading by file ──────────────────────────────────────────────────────────
CSV = """discipline,code,column,description,units,value,page
Physiotherapy,301,standard,Consultation 5-10 minutes,7.5,"184,08",329
Physiotherapy,302,standard,Consultation 11-20 minutes,15,368.59,329
Hospice,950,standard,"Ward fee, per day",,1 404.46,66
Hospice,960,standard,Global fee by arrangement,,,66
Hospice,970,standard,Bad amount,,"1,404.46",66
Hospice,980,standard,Negative,,-5,66
,,,,,,
Physiotherapy,301,standard,Printed twice,7.5,184.08,330
"""


def test_a_file_loads_what_it_can_and_reports_the_rest():
    _login()
    pl = _new("File list")
    r = client.post(f"{BASE}/{pl['id']}/import", json={"csv": CSV}).json()
    assert (r["added"], r["failed"], r["duplicates"]) == (5, 2, 1)
    assert any("row 6" in e and "comma and a point" in e for e in r["errors"])
    assert any("row 7" in e for e in r["errors"])
    rows = {(x["code"], x["description"]): x for x in _rows(pl["id"])["rows"]}
    # a single comma is the decimal mark; a space is a thousands separator
    assert rows[("301", "Consultation 5-10 minutes")]["value_rand"] == 184.08
    assert rows[("950", "Ward fee, per day")]["value_rand"] == 1404.46
    assert rows[("950", "Ward fee, per day")]["source_page"] == "66"
    # a row with no fee printed is still an entry
    assert rows[("960", "Global fee by arrangement")]["value_rand"] is None
    assert _rows(pl["id"], priced="none")["total"] == 1
    assert _rows(pl["id"], priced="value")["total"] == 4


def test_a_file_can_replace_a_drafts_entries_and_needs_a_usable_header():
    _login()
    pl = _new("Replace list")
    _entry(pl["id"], code="OLD")
    r = client.post(f"{BASE}/{pl['id']}/import",
                    json={"csv": "code,rate,colour\nN1,10\nN2,20\n", "mode": "replace"}).json()
    assert (r["added"], r["removed"], r["ignored_columns"]) == (2, 1, ["colour"])
    assert [x["code"] for x in _rows(pl["id"])["rows"]] == ["N1", "N2"]
    assert client.post(f"{BASE}/{pl['id']}/import", json={"csv": "name,amount\na,1\n"}).status_code == 422
    assert client.post(f"{BASE}/{pl['id']}/import", json={"csv": "code\n1\n"}).status_code == 422


def test_entries_can_be_searched_filtered_and_exported_back():
    _login()
    pl = _new("Search list")
    client.post(f"{BASE}/{pl['id']}/import", json={"csv": CSV})
    assert _rows(pl["id"], q="ward")["total"] == 1
    assert _rows(pl["id"], q="30")["total"] == 3
    assert _rows(pl["id"], discipline="Hospice")["total"] == 2
    page = client.get(f"{BASE}/{pl['id']}/entries", params={"limit": 2, "offset": 2}).json()
    assert page["total"] == 5 and [x["code"] for x in page["rows"]] == ["950", "960"]
    exported = client.get(f"{BASE}/{pl['id']}/export").text
    again = _new("Search list, reloaded")
    r = client.post(f"{BASE}/{again['id']}/import", json={"csv": exported}).json()
    assert (r["added"], r["failed"]) == (5, 0)
    strip = lambda rows: [{k: v for k, v in x.items() if k != "id"} for x in rows]  # noqa: E731
    assert strip(_rows(again["id"])["rows"]) == strip(_rows(pl["id"])["rows"])


def test_the_raf_tariff_extract_loads_through_the_same_door():
    _login()
    pl = _new("RAF Tariff 2021/2022 (test load)", legal_status="INTERDICTED",
              source="Government Gazette No. 46747, 19 August 2022")
    r = client.post(f"{BASE}/{pl['id']}/import", json={"csv": EXTRACT.read_text()}).json()
    assert r["failed"] == 0 and r["added"] == 15617, r["errors"][:3]
    got = client.get(f"{BASE}/{pl['id']}").json()
    assert len(got["disciplines"]) == 37
    assert "column_55700" in got["columns"] and "specialist" in got["columns"]
    hit = _rows(pl["id"], q="0190", discipline="medical_practitioners", column="specialist")["rows"]
    # the search also finds rows that mention the code in their text, so pick the code itself
    assert [(x["units"], x["value_rand"]) for x in hit if x["code"] == "0190"] == [(15.0, None)]
    odd = _rows(pl["id"], q="FCW223")["rows"][0]
    assert odd["alt_code"] == "JIR!J??3"          # kept exactly as the gazette prints it
    assert odd["note"] == "code_irregular_as_printed" and odd["source_page"] == "296"


# ── publishing ───────────────────────────────────────────────────────────────
def test_a_list_must_be_complete_to_publish_and_is_fixed_afterwards():
    _login()
    empty = client.post(BASE, json={"name": "Publish list"}).json()
    lid = empty["id"]
    assert "empty" in client.post(f"{BASE}/{lid}/publish").json()["detail"]
    e = _entry(lid)
    assert "takes effect" in client.post(f"{BASE}/{lid}/publish").json()["detail"]
    client.patch(f"{BASE}/{lid}", json={"effective_from": "2026-04-01"})
    assert "where the price list was published" in client.post(f"{BASE}/{lid}/publish").json()["detail"]
    client.patch(f"{BASE}/{lid}", json={"source": "Gazette 1"})
    done = client.post(f"{BASE}/{lid}/publish").json()
    assert done["state"] == "PUBLISHED" and done["published_by"] == "admin"
    # entries and header are now fixed
    for r in (client.post(f"{BASE}/{lid}/entries", json={"code": "9", "value_rand": 1}),
              client.patch(f"{BASE}/{lid}/entries/{e['id']}", json={"value_rand": 1}),
              client.delete(f"{BASE}/{lid}/entries/{e['id']}"),
              client.post(f"{BASE}/{lid}/import", json={"csv": "code,value_rand\n1,2\n"}),
              client.put(f"{BASE}/{lid}/factors", json={"factors": []}),
              client.patch(f"{BASE}/{lid}", json={"name": "Renamed"}),
              client.post(f"{BASE}/{lid}/publish"),
              client.delete(f"{BASE}/{lid}")):
        assert r.status_code == 409, r.text
    # notes stay editable
    assert client.patch(f"{BASE}/{lid}", json={"notes": "checked"}).json()["notes"] == "checked"
    assert _rows(lid)["rows"][0]["value_rand"] == 250.0


def test_legal_standing_can_change_after_publication_with_a_reason():
    _login()
    pl = _new("Standing list")
    _entry(pl["id"])
    client.post(f"{BASE}/{pl['id']}/publish")
    url = f"{BASE}/{pl['id']}/legal-status"
    assert client.post(url, json={"legal_status": "INTERDICTED", "reason": " "}).status_code == 422
    assert client.post(url, json={"legal_status": "ACCEPTED", "reason": "same"}).status_code == 409
    r = client.post(url, json={"legal_status": "INTERDICTED",
                               "reason": "Interdicted by the High Court on 1 May 2026"}).json()
    assert r["legal_status"] == "INTERDICTED" and "High Court" in r["status_note"]
    first = client.get(f"{BASE}/{pl['id']}/history").json()[0]
    assert first["action"] == "price_list.legal_status"
    assert (first["detail"]["from"], first["detail"]["to"]) == ("ACCEPTED", "INTERDICTED")
    assert first["actor"] == "admin"


def test_a_new_edition_starts_from_a_published_list_and_leaves_it_alone():
    _login()
    pl = _new("Edition 2026")
    _entry(pl["id"], code="301", value_rand=250.0)
    client.put(f"{BASE}/{pl['id']}/factors", json={"factors": [{"name": "rcf", "value": 16.05}]})
    client.post(f"{BASE}/{pl['id']}/publish")
    assert client.post(f"{BASE}/{pl['id']}/copy", json={"name": "Edition 2026"}).status_code == 409
    new = client.post(f"{BASE}/{pl['id']}/copy", json={"name": "Edition 2027", "edition": "2027"}).json()
    assert new["state"] == "DRAFT" and new["copied_from"] == pl["id"]
    assert new["copied_from_name"] == "Edition 2026" and new["effective_from"] is None
    assert new["factors"] == [{"name": "rcf", "value": 16.05}]
    e = _rows(new["id"])["rows"][0]
    client.patch(f"{BASE}/{new['id']}/entries/{e['id']}", json={"value_rand": 265.0})
    assert _rows(new["id"])["rows"][0]["value_rand"] == 265.0
    assert _rows(pl["id"])["rows"][0]["value_rand"] == 250.0


def test_retiring_and_deleting():
    _login()
    pl = _new("Retire list")
    _entry(pl["id"])
    assert client.post(f"{BASE}/{pl['id']}/retire", json={}).status_code == 409   # still a draft
    client.post(f"{BASE}/{pl['id']}/publish")
    early = client.post(f"{BASE}/{pl['id']}/retire", json={"effective_to": "2026-01-01"})
    assert early.status_code == 422
    r = client.post(f"{BASE}/{pl['id']}/retire",
                    json={"effective_to": "2027-03-31", "note": "superseded"}).json()
    assert (r["state"], r["effective_to"], r["retired_by"]) == ("RETIRED", "2027-03-31", "admin")
    assert client.patch(f"{BASE}/{pl['id']}", json={"notes": "x"}).status_code == 409
    assert client.post(f"{BASE}/{pl['id']}/legal-status",
                       json={"legal_status": "INTERDICTED", "reason": "x"}).status_code == 409
    assert client.delete(f"{BASE}/{pl['id']}").status_code == 409
    draft = _new("Delete list")
    _entry(draft["id"])
    assert client.delete(f"{BASE}/{draft['id']}").json() == {"deleted": draft["id"], "entries": 1}
    assert client.get(f"{BASE}/{draft['id']}").status_code == 404
    with SessionLocal() as db:
        assert db.scalar(select(func.count(models.RefPriceListEntry.id))
                         .where(models.RefPriceListEntry.list_id == draft["id"])) == 0


# ── the boundary with pricing ────────────────────────────────────────────────
def _pricing_state():
    with SessionLocal() as db:
        return (db.scalar(select(func.count()).select_from(models.RefRpl)),
                db.scalar(select(func.count()).select_from(models.RefRaf2022)),
                db.scalar(select(func.count()).select_from(models.RefRateVersion)),
                db.scalar(select(func.count()).select_from(models.RefNegotiated)),
                db.scalar(select(func.count()).select_from(models.RefRateLog)))


def test_holding_and_publishing_a_list_prices_nothing():
    _login()
    before = _pricing_state()
    quote = client.get("/api/rates", params={"source": "RPL"}).json()
    pl = _new("Boundary list")
    client.post(f"{BASE}/{pl['id']}/import", json={"csv": CSV})
    client.post(f"{BASE}/{pl['id']}/publish")
    client.post(f"{BASE}/{pl['id']}/legal-status",
                json={"legal_status": "ENFORCEABLE", "reason": "agreed with the Fund"})
    assert _pricing_state() == before
    assert client.get("/api/rates", params={"source": "RPL"}).json() == quote


def test_every_change_is_in_the_audit_trail():
    _login()
    pl = _new("Trail list")
    e = _entry(pl["id"])
    client.patch(f"{BASE}/{pl['id']}/entries/{e['id']}", json={"value_rand": 300})
    client.post(f"{BASE}/{pl['id']}/import", json={"csv": "code,value_rand\nX1,5\n"})
    client.patch(f"{BASE}/{pl['id']}", json={"edition": "2026 rev 1"})
    client.post(f"{BASE}/{pl['id']}/publish")
    actions = [h["action"] for h in client.get(f"{BASE}/{pl['id']}/history").json()]
    assert actions == ["price_list.publish", "price_list.update", "price_list.import",
                       "price_list.entry.update", "price_list.entry.add", "price_list.create"]
    hist = client.get(f"{BASE}/{pl['id']}/history").json()
    assert hist[3]["detail"]["changed"] == {"value_rand": {"from": 250.0, "to": 300.0}}
    assert hist[1]["detail"]["changed"]["edition"] == {"from": "2026", "to": "2026 rev 1"}
