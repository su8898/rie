"""Medical reports (port of CIE's statutory medical report forms, adapted to RAF 1 and RAF 4):
filed by a provider over the rails channel, stored against the claim as received, judged for
completeness by the Fund, and printable. A complete RAF 4 opens the serious-injury assessment."""
from __future__ import annotations

import time
import uuid
import xml.etree.ElementTree as ET

import test_api  # noqa: F401  (sets RIE_DATABASE_URL + imports the app first)
from fastapi.testclient import TestClient
from sqlalchemy import select

from server import jws, medical_report_service as svc, models
from server.db import SessionLocal
from server.main import app

ops = TestClient(app)                                    # the Fund's operators (session cookie)
provider = TestClient(app)                               # a provider system (JWS only, no session)
SECRET = "rie-rails-dev-secret"

RAF1 = {"first_treated_on": "2026-02-01", "facility": "Tembisa Hospital", "admitted": "Yes",
        "nature_of_injuries": "Closed fracture of the right femur", "icd10": "S72.3",
        "consistent": "Yes", "treatment": "Open reduction and internal fixation",
        "practitioner_name": "Dr A Practitioner", "registration_number": "MP0123456",
        "declared_on": "2026-03-01", "signed": "Yes"}
RAF4 = {"assessed_on": "2026-06-01", "accident_date": "2026-02-01", "mmi_reached": "Yes",
        "diagnosis": "Malunited femur fracture with shortening", "non_serious_list": "No",
        "wpi": "35", "narrative_function": "No", "narrative_disfigurement": "No",
        "narrative_mental": "No", "narrative_foetus": "No",
        "practitioner_name": "Dr A Practitioner", "registration_number": "MP0123456",
        "declared_on": "2026-06-01", "signed": "Yes"}


def _login(user="handler"):
    assert ops.post("/api/auth/login", json={"username": user, "password": user}).status_code == 200


def _claim(cid, party, cas, ctype="SUPPLIER"):
    docs = ({"RAF2": True, "OAR": True, "INVOICES": True, "BANK": True} if ctype == "SUPPLIER"
            else {"RAF1": True, "OAR": True, "ID": True, "BANK": True})
    _login()
    r = ops.post("/api/claims", json={
        "claim_id": cid, "claim_type": ctype, "party_token": party, "case_number_raw": cas,
        "accident_date": "2026-02-01", "lodged_on": "2026-03-01", "today": "2026-07-05",
        "payee_verified": True, "documents": docs,
        "lines": [{"kind": "TARIFF", "code": "0190", "qty": 1, "amount": 500.0,
                   "service_date": "2026-03-01", "provider_id": "PR_MR", "dx": "S72"}]})
    assert r.status_code == 200, r.text


def _body(form_code, claim_ref, values, provider_id="PR_MR", extra_sections=()):
    """A filing laid out from the Fund's own catalogue, carrying only the values given."""
    sections = [{"key": s["key"], "title": s["title"],
                 "fields": [{"key": f["key"], "label": f["label"], "value": values[f["key"]]}
                            for f in s["fields"] if f["key"] in values]}
                for s in svc.FORMS[form_code]["sections"]]
    return {"form_code": form_code, "provider_id": provider_id, "claim_ref": claim_ref,
            "sections": sections + list(extra_sections)}


def _sig(obj, exp=None, jti=True):
    header = {"alg": "HS256", "exp": exp or int(time.time()) + 300}
    if jti:
        header["jti"] = jti if isinstance(jti, str) else str(uuid.uuid4())
    return {"X-JWS-Signature": jws.sign_detached(header, obj, SECRET)}


def _file(body, key=None, **kw):
    return provider.post("/rails/v1/medical-reports", json=body,
                         headers={"Idempotency-Key": key or str(uuid.uuid4()), **_sig(body, **kw)})


# ── the catalogue ────────────────────────────────────────────────────────────
def test_catalogue_names_both_forms_and_their_required_fields():
    assert provider.get("/rails/v1/medical-reports/forms").status_code == 401
    forms = provider.get("/rails/v1/medical-reports/forms",
                         headers=_sig({"catalogue": "medical-report-forms"})).json()
    assert [f["form_code"] for f in forms] == ["RAF1-MR", "RAF4"]
    raf4 = forms[1]
    assert "regulation 3" in raf4["basis"] and raf4["title"].startswith("RAF 4")
    required = [f["key"] for s in raf4["sections"] for f in s["fields"] if f["required"]]
    assert "wpi" in required and "narrative_function" in required and "wpi_basis" not in required
    _login()
    assert ops.get("/api/medical-reports/forms").json() == forms          # one catalogue, both sides


# ── filing ───────────────────────────────────────────────────────────────────
def test_complete_report_is_stored_against_its_claim_and_printable():
    _claim("R_MR_1", "P_MR_1", "CAS 9601/02/2026")
    r = _file(_body("RAF1-MR", "R_MR_1", RAF1))
    assert r.status_code == 200, r.text
    j = r.json()
    ref = j["ref"]
    assert ref.startswith("MR-") and j["form_code"] == "RAF1-MR" and j["claim_id"] == "R_MR_1"
    assert j["complete"] is True and j["missing"] == [] and j["idempotentReplay"] is False
    assert j["seriousInjury"] is None and j["form_title"].startswith("RAF 1")

    _login()                                                 # the operator's view of the same report
    mine = ops.get("/api/medical-reports", params={"claim_id": "R_MR_1"}).json()
    assert [m["ref"] for m in mine] == [ref] and "sections" not in mine[0]
    full = ops.get(f"/api/medical-reports/{ref}").json()
    injuries = next(s for s in full["sections"] if s["key"] == "injuries")
    assert {"key": "icd10", "label": "ICD-10 codes", "value": "S72.3"} in injuries["fields"]

    root = ET.fromstring(ops.get(f"/api/medical-reports/{ref}/xml").text)
    assert root.tag == "MedicalReport" and root.get("form") == "RAF1-MR"
    assert root.findtext("ReportRef") == ref and root.findtext("Complete") == "true"
    assert root.find("Section[@key='care']/Field[@key='treatment']").text == "Open reduction and internal fixation"

    page = ops.get(f"/api/medical-reports/{ref}/print")
    assert page.status_code == 200 and "default-src 'none'" in page.headers["content-security-policy"]
    assert "Closed fracture of the right femur" in page.text and "<script" not in page.text
    assert "Road Accident Fund Act s24(2)(a)" in page.text and "Incomplete" not in page.text

    # the provider reads its own over the rails
    got = provider.get(f"/rails/v1/medical-reports/{ref}", headers=_sig({"reportRef": ref})).json()
    assert got["ref"] == ref and got["sections"] == full["sections"]
    as_xml = provider.get(f"/rails/v1/medical-reports/{ref}", params={"format": "xml"},
                          headers=_sig({"reportRef": ref}))
    assert ET.fromstring(as_xml.text).findtext("Provider") == "PR_MR"
    listed = provider.get("/rails/v1/medical-reports", params={"provider_id": "PR_MR"},
                          headers=_sig({"providerId": "PR_MR"})).json()
    assert ref in [x["ref"] for x in listed]


def test_the_fund_judges_completeness_and_names_what_is_missing():
    _claim("R_MR_2", "P_MR_2", "CAS 9602/02/2026")
    partial = {k: v for k, v in RAF1.items() if k not in ("icd10", "signed")}
    partial["treatment"] = "  "                              # present but empty counts as missing
    j = _file(_body("RAF1-MR", "R_MR_2", partial)).json()
    assert j["complete"] is False
    assert j["missing"] == ["ICD-10 codes", "Treatment given", "Declaration signed (Yes/No)"]

    _login()
    doc = ops.get("/api/medical-reports/documentation/R_MR_2").json()["forms"]
    assert doc["RAF1-MR"]["on_file"] is True and doc["RAF1-MR"]["complete"] is False
    assert doc["RAF4"] == {"title": svc.FORMS["RAF4"]["title"], "on_file": False, "complete": False, "reports": []}
    page = ops.get(f"/api/medical-reports/{j['ref']}/print").text
    assert "Incomplete. Still required: ICD-10 codes; Treatment given" in page

    done = _file(_body("RAF1-MR", "R_MR_2", RAF1)).json()    # the corrected report is a new filing
    doc = provider.get("/rails/v1/claims/R_MR_2/documentation", headers=_sig({"claimId": "R_MR_2"})).json()
    assert doc["forms"]["RAF1-MR"]["complete"] is True
    assert doc["forms"]["RAF1-MR"]["reports"] == [done["ref"], j["ref"]]
    assert provider.get("/rails/v1/claims/R_MR_2/documentation").status_code == 401
    assert provider.get("/rails/v1/claims/R_NOPE/documentation",
                        headers=_sig({"claimId": "R_NOPE"})).status_code == 404


def test_sections_outside_the_catalogue_are_kept_as_filed():
    _claim("R_MR_3", "P_MR_3", "CAS 9603/02/2026")
    extra = [{"title": "Radiology", "fields": [{"label": "X-ray findings", "value": "Displaced, 2 cm"}]}]
    j = _file(_body("RAF1-MR", "R_MR_3", RAF1, extra_sections=extra)).json()
    assert j["complete"] is True
    assert j["sections"][-1] == {"key": "", "title": "Radiology",
                                 "fields": [{"key": "", "label": "X-ray findings", "value": "Displaced, 2 cm"}]}
    _login()
    assert "X-ray findings" in ops.get(f"/api/medical-reports/{j['ref']}/print").text


# ── RAF 4 and the serious-injury assessment ──────────────────────────────────
def test_complete_raf4_opens_the_serious_injury_assessment_once():
    _claim("R_MR_SI", "P_MR_SI", "CAS 9610/02/2026", ctype="PERSONAL")
    j = _file(_body("RAF4", "R_MR_SI", RAF4)).json()
    assert j["complete"] is True and j["seriousInjury"]["status"] == "SUBMITTED"
    with SessionLocal() as db:
        si = db.get(models.SeriousInjury, j["seriousInjury"]["id"])
        assert (si.claim_id, si.status, si.wpi, si.narrative, si.list_match) == \
               ("R_MR_SI", "SUBMITTED", 35.0, False, False)
    again = _file(_body("RAF4", "R_MR_SI", {**RAF4, "wpi": "40"})).json()   # a second RAF 4 opens nothing new
    assert again["complete"] is True and again["seriousInjury"] is None
    with SessionLocal() as db:
        assert len(list(db.scalars(select(models.SeriousInjury)
                                   .where(models.SeriousInjury.claim_id == "R_MR_SI")))) == 1


def test_raf4_carries_the_narrative_finding_and_tolerates_a_loose_percentage():
    _claim("R_MR_SI2", "P_MR_SI2", "CAS 9611/02/2026", ctype="PERSONAL")
    j = _file(_body("RAF4", "R_MR_SI2", {**RAF4, "wpi": " 12 % ", "narrative_mental": "yes"})).json()
    with SessionLocal() as db:
        si = db.get(models.SeriousInjury, j["seriousInjury"]["id"])
        assert si.wpi == 12.0 and si.narrative is True
    assert [svc._wpi(x) for x in ("35", "35 %", "about a third", "150", None)] == [35.0, 35.0, None, None, None]


def test_raf4_opens_nothing_when_incomplete_or_not_on_a_personal_claim():
    _claim("R_MR_SI3", "P_MR_SI3", "CAS 9612/02/2026", ctype="PERSONAL")
    _claim("R_MR_SI4", "P_MR_SI4", "CAS 9613/02/2026")                    # a supplier claim
    incomplete = _file(_body("RAF4", "R_MR_SI3", {k: v for k, v in RAF4.items() if k != "wpi"})).json()
    assert incomplete["complete"] is False and incomplete["seriousInjury"] is None
    assert incomplete["missing"] == ["Whole person impairment (%)"]
    assert _file(_body("RAF4", "R_MR_SI4", RAF4)).json()["seriousInjury"] is None
    assert _file(_body("RAF1-MR", "R_MR_SI3", RAF1)).json()["seriousInjury"] is None


# ── a report that arrives before its claim ───────────────────────────────────
def test_report_filed_before_its_claim_is_tied_to_it_later():
    j = _file(_body("RAF1-MR", "R_MR_LATE", RAF1)).json()
    assert j["claim_id"] is None and j["claim_ref"] == "R_MR_LATE" and j["complete"] is True
    _login()
    assert ops.get("/api/medical-reports", params={"claim_id": "R_MR_LATE"}).json() == []   # no such claim yet
    _claim("R_MR_LATE", "P_MR_LATE", "CAS 9620/02/2026")
    mine = ops.get("/api/medical-reports", params={"claim_id": "R_MR_LATE"}).json()
    assert [m["ref"] for m in mine] == [j["ref"]] and mine[0]["claim_id"] == "R_MR_LATE"
    assert ops.get("/api/medical-reports/documentation/R_NOPE").status_code == 404


# ── idempotency, replay and signature ────────────────────────────────────────
def test_retried_filing_returns_the_same_report():
    _claim("R_MR_IDEM", "P_MR_IDEM", "CAS 9630/02/2026")
    body, key = _body("RAF1-MR", "R_MR_IDEM", RAF1), str(uuid.uuid4())
    first = _file(body, key=key).json()
    retry = _file(body, key=key).json()                      # a fresh nonce, the same key and body
    assert retry["ref"] == first["ref"] and retry["idempotentReplay"] is True
    clash = _file({**body, "provider_id": "PR_OTHER"}, key=key)
    assert clash.status_code == 409 and "different body" in clash.json()["detail"]
    with SessionLocal() as db:
        assert len(list(db.scalars(select(models.MedicalReport)
                                   .where(models.MedicalReport.claim_ref == "R_MR_IDEM")))) == 1


def test_filing_guards():
    body = _body("RAF1-MR", "R_MR_1", RAF1)
    assert provider.post("/rails/v1/medical-reports", json=body,
                         headers={"Idempotency-Key": "k"}).status_code == 401              # unsigned
    assert provider.post("/rails/v1/medical-reports", json=body, headers=_sig(body)).status_code == 400   # no key
    assert _file(body, jti=False).status_code == 400                                       # no nonce
    assert _file(body, exp=int(time.time()) - 5).status_code == 401                        # expired
    nonce = str(uuid.uuid4())
    assert _file(body, jti=nonce).status_code == 200
    assert _file(body, jti=nonce).status_code == 409                                       # replayed nonce
    assert provider.get("/rails/v1/medical-reports/MR-NOPE", headers=_sig({"reportRef": "MR-NOPE"})).status_code == 404
    assert provider.get("/rails/v1/medical-reports", params={"provider_id": "PR_MR"}).status_code == 401
    assert TestClient(app).get("/api/medical-reports").status_code == 401
    _login()
    assert ops.get("/api/medical-reports/MR-NOPE").status_code == 404


def test_filing_validation():
    ok = _body("RAF1-MR", "R_MR_1", RAF1)

    def bad(**change):
        return _file({**ok, **change}).json()["detail"]

    assert "form_code must be one of" in bad(form_code="W.Cl.4")
    assert "provider_id and claim_ref are required" in bad(provider_id="")
    assert "provider_id and claim_ref are required" in bad(claim_ref="x" * 65)
    for sections in (None, [], "text", [{}] * 41):
        assert "sections must be a list" in bad(sections=sections)
    assert "needs a fields list" in bad(sections=[{"title": "x"}])
    assert "needs a fields list" in bad(sections=["not a section"])
    assert "needs a fields list" in bad(sections=[{"fields": [{"label": "a"}] * 81}])
    assert "needs a label" in bad(sections=[{"fields": [{"value": "v"}]}])
    assert "needs a label" in bad(sections=[{"fields": ["x"]}])
    assert "at most" in bad(sections=[{"fields": [{"label": "a", "value": "v" * 4001}]}])
    assert "at most" in bad(sections=[{"fields": [{"label": "a" * 201}]}])
    assert "identity number must not be sent" in bad(
        sections=[{"fields": [{"label": "Patient ID", "value": "8001015009087"}]}])


def test_hostile_content_is_escaped_in_both_formats():
    evil = '<img src=x onerror="alert(1)"> & "quotes"'
    j = _file(_body("RAF1-MR", "R_MR_1", {**RAF1, "nature_of_injuries": evil},
                    provider_id='PR<&"x', extra_sections=[{"title": evil, "fields": [{"label": evil}]}])).json()
    _login()
    root = ET.fromstring(ops.get(f"/api/medical-reports/{j['ref']}/xml").text)
    assert root.findtext("Provider") == 'PR<&"x'
    assert root.find("Section[@key='injuries']/Field[@key='nature_of_injuries']").text == evil
    page = ops.get(f"/api/medical-reports/{j['ref']}/print").text
    assert "<img" not in page and "&lt;img src=x" in page and "&mdash;" in page      # an empty value prints as a dash
