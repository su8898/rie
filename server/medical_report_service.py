"""Medical reports — the statutory forms a PROVIDER completes and files with the Fund (port of
CIE's medical reports, adapted to the Road Accident Fund's forms).

Two forms are catalogued: the medical report in the RAF 1 claim form, completed by the treating
practitioner, and the RAF 4 serious injury assessment report. A provider's system files the
completed form over the rails channel; the Fund stores it against the claim it quotes, exactly as
filed, and both sides can print it. A filing is self-describing (sections -> fields ->
{label, value}), so a form the catalogue does not know in full is still kept whole.

The Fund, not the provider, decides whether a report is complete: every field the catalogue marks
required must carry a value. A complete RAF 4 on a personal claim that has no serious-injury
assessment yet opens one, SUBMITTED, for the medical officer.

The patient is identified by the claim reference only. A bare 13-digit identity number anywhere in
a filing is refused.

THE FIELD LISTS BELOW ARE WORKING LAYOUTS. Check them against the gazetted RAF 1 and RAF 4 before
go-live; changing a layout is an edit to FORMS, not to the storage or the wire format.
"""
from __future__ import annotations

import hashlib
import uuid
from typing import Optional
from xml.sax.saxutils import escape, quoteattr

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import jws, models, serious_injury_service
from .pseudonymise import RAW_SA_ID

MAX_SECTIONS, MAX_FIELDS, MAX_LABEL, MAX_VALUE = 40, 80, 200, 4000


def _f(key: str, label: str, required: bool = False) -> dict:
    return {"key": key, "label": label, "required": required}


_DECLARATION = {"key": "declaration", "title": "Practitioner declaration", "fields": [
    _f("practitioner_name", "Name of the medical practitioner", True),
    _f("qualifications", "Qualifications"),
    _f("registration_number", "HPCSA registration number", True),
    _f("practice_number", "Practice number"),
    _f("declared_on", "Date of declaration", True),
    _f("signed", "Declaration signed (Yes/No)", True),
]}

FORMS: dict[str, dict] = {
    "RAF1-MR": {
        "title": "RAF 1: medical report by the treating practitioner",
        "basis": "Road Accident Fund Act s24(2)(a) — the medical report in the claim form",
        "sections": [
            {"key": "treatment", "title": "First treatment", "fields": [
                _f("first_treated_on", "Date of first treatment or admission", True),
                _f("facility", "Hospital or practice where treated", True),
                _f("admitted", "Admitted to hospital (Yes/No)"),
                _f("hospital_period", "Period of hospitalisation"),
            ]},
            {"key": "injuries", "title": "Injuries", "fields": [
                _f("nature_of_injuries", "Nature of the bodily injuries sustained", True),
                _f("icd10", "ICD-10 codes", True),
                _f("consistent", "Injuries consistent with a motor vehicle accident (Yes/No)", True),
                _f("pre_existing", "Pre-existing conditions relevant to the injuries"),
            ]},
            {"key": "care", "title": "Treatment given", "fields": [
                _f("treatment", "Treatment given", True),
                _f("procedures", "Operations or procedures performed"),
                _f("further_treatment", "Further treatment expected"),
            ]},
            {"key": "outcome", "title": "Outcome", "fields": [
                _f("temporary_disability", "Period of temporary disability"),
                _f("permanent_disability", "Permanent disability expected (Yes/No)"),
                _f("prognosis", "Prognosis"),
                _f("death", "If the patient died: date and cause of death"),
            ]},
            _DECLARATION,
        ],
    },
    "RAF4": {
        "title": "RAF 4: serious injury assessment report",
        "basis": "Road Accident Fund Regulations, regulation 3 — assessment of serious injury",
        "sections": [
            {"key": "assessment", "title": "Assessment", "fields": [
                _f("assessed_on", "Date of assessment", True),
                _f("accident_date", "Date of accident", True),
                _f("mmi_reached", "Maximum medical improvement reached (Yes/No)", True),
                _f("mmi_date", "Date maximum medical improvement was reached"),
            ]},
            {"key": "injuries", "title": "Injuries assessed", "fields": [
                _f("diagnosis", "Diagnosis of the injuries assessed", True),
                _f("icd10", "ICD-10 codes"),
                _f("non_serious_list", "Injury appears only on the list of non-serious injuries (Yes/No)", True),
            ]},
            {"key": "wpi", "title": "Whole person impairment (AMA Guides, sixth edition)", "fields": [
                _f("wpi", "Whole person impairment (%)", True),
                _f("wpi_basis", "Chapters and tables applied"),
            ]},
            {"key": "narrative", "title": "Narrative test", "fields": [
                _f("narrative_function", "Serious long-term impairment or loss of a body function (Yes/No)", True),
                _f("narrative_disfigurement", "Permanent serious disfigurement (Yes/No)", True),
                _f("narrative_mental", "Severe long-term mental or behavioural disturbance or disorder (Yes/No)", True),
                _f("narrative_foetus", "Loss of a foetus (Yes/No)", True),
                _f("narrative_reasons", "Reasons for the narrative finding"),
            ]},
            _DECLARATION,
        ],
    },
}
_NARRATIVE_KEYS = ("narrative_function", "narrative_disfigurement", "narrative_mental", "narrative_foetus")


class ReportError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def catalogue() -> list[dict]:
    """The forms the Fund accepts, with their sections and which fields a complete report needs."""
    return [{"form_code": code, **form} for code, form in FORMS.items()]


# ── the filing: validate, normalise, judge completeness ──────────────────────
def _clean(body: dict) -> list[dict]:
    """The filing's sections as stored: every label and value a bounded string, catalogue keys
    kept, nothing else carried. A bare 13-digit identity number is refused."""
    sections = body.get("sections")
    if not isinstance(sections, list) or not sections or len(sections) > MAX_SECTIONS:
        raise ReportError(422, f"sections must be a list of 1 to {MAX_SECTIONS} sections")
    out = []
    for s in sections:
        fields = s.get("fields") if isinstance(s, dict) else None
        if not isinstance(fields, list) or len(fields) > MAX_FIELDS:
            raise ReportError(422, f"each section needs a fields list of at most {MAX_FIELDS} fields")
        clean = []
        for f in fields:
            if not isinstance(f, dict) or not str(f.get("label") or "").strip():
                raise ReportError(422, "each field needs a label")
            label, value = str(f["label"]).strip(), str(f.get("value") if f.get("value") is not None else "").strip()
            if len(label) > MAX_LABEL or len(value) > MAX_VALUE:
                raise ReportError(422, f"a label is at most {MAX_LABEL} and a value {MAX_VALUE} characters")
            if RAW_SA_ID.match(value):
                raise ReportError(422, "an identity number must not be sent in a report — "
                                       "the patient is identified by the claim reference")
            clean.append({"key": str(f.get("key") or "").strip()[:64], "label": label, "value": value})
        out.append({"key": str(s.get("key") or "").strip()[:64],
                    "title": str(s.get("title") or "").strip()[:MAX_LABEL], "fields": clean})
    return out


def _values(sections: list[dict]) -> dict[str, str]:
    """Catalogue key -> value, for the fields a filing carried with a key."""
    return {f["key"]: f["value"] for s in sections for f in s["fields"] if f["key"]}


def _missing(form_code: str, sections: list[dict]) -> list[str]:
    """Labels of the required catalogue fields the filing left out or left empty."""
    have = _values(sections)
    return [f["label"] for s in FORMS[form_code]["sections"] for f in s["fields"]
            if f["required"] and not have.get(f["key"])]


def _yes(value: Optional[str]) -> bool:
    return str(value or "").strip().lower() in ("yes", "y", "true")


def _wpi(value: Optional[str]) -> Optional[float]:
    try:
        wpi = float(str(value or "").strip().rstrip("%").strip())
    except ValueError:
        return None
    return wpi if 0 <= wpi <= 100 else None


def _open_serious_injury(db: Session, report: "models.MedicalReport") -> Optional[int]:
    """A complete RAF 4 on a personal claim with no serious-injury assessment yet opens one for
    the medical officer, carrying the form's impairment figure and narrative finding."""
    claim = db.get(models.ClaimRecord, report.claim_id) if report.claim_id else None
    if report.form_code != "RAF4" or not report.complete or claim is None or claim.claim_type != "PERSONAL":
        return None
    if db.scalar(select(models.SeriousInjury.id).where(models.SeriousInjury.claim_id == claim.claim_id).limit(1)):
        return None
    values = _values(report.sections)
    si = serious_injury_service.create(db, claim.claim_id, list_match=False, wpi=_wpi(values.get("wpi")),
                                       narrative=any(_yes(values.get(k)) for k in _NARRATIVE_KEYS))
    return si.id


def receive(db: Session, body: dict, idempotency_key: Optional[str]) -> dict:
    """File a report. The same Idempotency-Key with the same body returns the stored report; with
    a different body it is refused. The caller has already verified the signature and nonce."""
    if not idempotency_key:
        raise ReportError(400, "Idempotency-Key header required")
    body_hash = hashlib.sha256(jws.canonical(body)).hexdigest()
    existing = db.scalar(select(models.MedicalReport)
                         .where(models.MedicalReport.idempotency_key == idempotency_key))
    if existing is not None:
        if existing.body_hash != body_hash:
            raise ReportError(409, "Idempotency-Key reused with a different body")
        return {**detail(existing), "idempotentReplay": True, "seriousInjury": None}

    form_code = str(body.get("form_code") or "").strip().upper()
    provider_id = str(body.get("provider_id") or "").strip()
    claim_ref = str(body.get("claim_ref") or "").strip()
    if form_code not in FORMS:
        raise ReportError(422, f"form_code must be one of {sorted(FORMS)}")
    if not provider_id or not claim_ref or len(provider_id) > 64 or len(claim_ref) > 64:
        raise ReportError(422, "provider_id and claim_ref are required (at most 64 characters each)")
    sections = _clean(body)
    missing = _missing(form_code, sections)
    claim = db.get(models.ClaimRecord, claim_ref)
    report = models.MedicalReport(
        ref="MR-" + uuid.uuid4().hex[:10].upper(), form_code=form_code,
        form_title=FORMS[form_code]["title"], provider_id=provider_id, claim_ref=claim_ref,
        claim_id=claim.claim_id if claim is not None else None, complete=not missing,
        missing=missing, sections=sections, idempotency_key=idempotency_key, body_hash=body_hash)
    db.add(report)
    db.flush()
    si_id = _open_serious_injury(db, report)
    db.commit()
    return {**detail(report), "idempotentReplay": False,
            "seriousInjury": {"id": si_id, "status": "SUBMITTED"} if si_id else None}


# ── reads ────────────────────────────────────────────────────────────────────
def summary(r: "models.MedicalReport") -> dict:
    return {"ref": r.ref, "form_code": r.form_code, "form_title": r.form_title,
            "provider_id": r.provider_id, "claim_ref": r.claim_ref, "claim_id": r.claim_id,
            "complete": r.complete, "missing": list(r.missing or []),
            "received_at": r.received_at.isoformat() if r.received_at else None}


def detail(r: "models.MedicalReport") -> dict:
    return {**summary(r), "sections": list(r.sections or [])}


def get(db: Session, ref: str) -> dict:
    r = db.scalar(select(models.MedicalReport).where(models.MedicalReport.ref == ref))
    if r is None:
        raise ReportError(404, "medical report not found")
    return detail(r)


def _resolve_late(db: Session, claim_id: str) -> None:
    """A report filed before its claim existed is tied to the claim the first time it is asked for."""
    late = list(db.scalars(select(models.MedicalReport).where(
        models.MedicalReport.claim_ref == claim_id, models.MedicalReport.claim_id.is_(None))))
    if late and db.get(models.ClaimRecord, claim_id) is not None:
        for r in late:
            r.claim_id = claim_id
        db.commit()


def list_reports(db: Session, provider_id: Optional[str] = None, claim_id: Optional[str] = None,
                 limit: int = 200) -> list[dict]:
    stmt = select(models.MedicalReport).order_by(models.MedicalReport.id.desc()).limit(limit)
    if provider_id:
        stmt = stmt.where(models.MedicalReport.provider_id == provider_id)
    if claim_id:
        _resolve_late(db, claim_id)
        stmt = stmt.where(models.MedicalReport.claim_id == claim_id)
    return [summary(r) for r in db.scalars(stmt)]


def documentation(db: Session, claim_id: str) -> dict:
    """Which catalogued forms are on file for a claim, and whether a complete one is among them."""
    if db.get(models.ClaimRecord, claim_id) is None:
        raise ReportError(404, "claim not found")
    reports = list_reports(db, claim_id=claim_id)
    forms = {}
    for code, form in FORMS.items():
        mine = [r for r in reports if r["form_code"] == code]
        forms[code] = {"title": form["title"], "on_file": bool(mine),
                       "complete": any(r["complete"] for r in mine),
                       "reports": [r["ref"] for r in mine]}
    return {"claim_id": claim_id, "forms": forms}


# ── wire format: <MedicalReport> XML ─────────────────────────────────────────
def to_xml(d: dict) -> str:
    def a(v) -> str:
        return quoteattr(str(v if v is not None else ""))

    sections = "".join(
        f'<Section key={a(s["key"])} title={a(s["title"])}>'
        + "".join(f'<Field key={a(f["key"])} label={a(f["label"])}>{escape(f["value"])}</Field>'
                  for f in s["fields"])
        + "</Section>" for s in d["sections"])
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<MedicalReport form={a(d["form_code"])} title={a(d["form_title"])}>'
            f'<ReportRef>{escape(d["ref"])}</ReportRef>'
            f'<Provider>{escape(d["provider_id"])}</Provider>'
            f'<ClaimRef>{escape(d["claim_ref"])}</ClaimRef>'
            f'<Complete>{"true" if d["complete"] else "false"}</Complete>'
            f'{sections}</MedicalReport>')


# ── print format ─────────────────────────────────────────────────────────────
def print_html(d: dict) -> str:
    """A print-ready report. Every value is escaped; nothing here is executable."""
    sections = ""
    for s in d["sections"]:
        rows = "".join(f'<tr><td class="lbl">{escape(f["label"])}</td>'
                       f'<td class="val">{escape(f["value"]) or "&mdash;"}</td></tr>' for f in s["fields"])
        sections += f'<h2>{escape(s["title"])}</h2><table>{rows}</table>'
    missing = (f'<div class="warn">Incomplete. Still required: {escape("; ".join(d["missing"]))}.</div>'
               if d["missing"] else "")
    basis = escape(FORMS[d["form_code"]]["basis"])
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>{escape(d["form_code"])} {escape(d["ref"])}</title>
<style>
 body{{font:13px/1.5 -apple-system,Segoe UI,sans-serif;color:#1a1a1a;max-width:800px;margin:24px auto;padding:0 16px}}
 .hdr{{border-bottom:2px solid #1f2937;padding-bottom:8px;margin-bottom:12px}}
 .code{{font-weight:700;font-size:12px;letter-spacing:.5px}} h1{{font-size:17px;margin:2px 0 0}}
 .basis{{color:#5b6b76;font-size:11px;margin-top:2px}}
 .meta{{display:grid;grid-template-columns:150px 1fr;gap:1px 12px;margin:8px 0 14px;font-size:12px}} .meta b{{color:#5b6b76;font-weight:500}}
 h2{{font-size:12px;text-transform:uppercase;letter-spacing:.4px;margin:16px 0 4px;border-bottom:1px solid #dce4ea;padding-bottom:2px}}
 table{{width:100%;border-collapse:collapse;font-size:12px}} td{{padding:4px 8px;border-bottom:1px solid #eef2f5;vertical-align:top}}
 td.lbl{{width:46%;color:#5b6b76}} td.val{{font-weight:500;white-space:pre-wrap}}
 .warn{{margin:10px 0;padding:6px 10px;border:1px solid #f0c2a8;background:#fff6f0;color:#9a3412;font-size:12px}}
 .note{{margin-top:18px;font-size:11px;color:#5b6b76;border-top:1px solid #dce4ea;padding-top:8px}}
 @media print{{body{{margin:0}}}}
</style></head><body>
<div class="hdr"><div class="code">{escape(d["form_code"])} · ROAD ACCIDENT FUND</div><h1>{escape(d["form_title"])}</h1>
  <div class="basis">{basis}</div></div>
<div class="meta">
  <b>Fund reference</b><span>{escape(d["ref"])}</span>
  <b>Provider</b><span>{escape(d["provider_id"])}</span>
  <b>Claim reference</b><span>{escape(d["claim_ref"])}</span>
  <b>Received</b><span>{escape(d["received_at"] or "")}</span>
  <b>Status</b><span>{"Complete" if d["complete"] else "Incomplete"}</span>
</div>
{missing}{sections}
<div class="note">Filed electronically by the provider named above and stored as received. The patient is identified by the claim reference.</div>
</body></html>"""
