"""Switch message intake — a BHF `<Claims>` XML message, as a practice-management system or a
switch already produces it, mapped onto the rails claim and scored like any other submission
(port of CIE's switch intake).

The message travels inside the ordinary signed JSON envelope, `{"format": "BHF_XML", "message":
"<Claims>…"}`, so signing, replay protection, idempotency and provider scoping are exactly those
of a JSON claim. Two elements are Road Accident Fund extensions to the header: `<AccidentDate>`
(required — a claim is anchored to its accident) and `<CaseNumber>` (the police case number).

The patient's identity number in the message is tokenised on receipt and never stored. A message
carries no document checklist, so the claim is scored and then held for validation until the Fund
confirms its supporting documents.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from . import rails_service

FORMATS = {"BHF_XML"}
MAX_MESSAGE = 1_000_000                               # characters
_HOSPITAL_POS = {"21", "22", "23", "24"}              # hospital / emergency-unit place of service
_NAPPI_TYPES = {"NAPPI", "MEDICINE"}


class SwitchError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def _text(node, path: str) -> str:
    found = node.find(path) if node is not None else None
    return (found.text or "").strip() if found is not None else ""


def _date(value: str, field: str, required: bool = False) -> Optional[str]:
    """`20260302` or `2026-03-02` -> ISO date string."""
    v = value.strip()
    if not v:
        if required:
            raise SwitchError(422, f"the message has no {field}")
        return None
    try:
        return (date(int(v[:4]), int(v[4:6]), int(v[6:8])) if len(v) == 8 and v.isdigit()
                else date.fromisoformat(v)).isoformat()
    except ValueError:
        raise SwitchError(422, f"{field} is not a date (YYYYMMDD or YYYY-MM-DD)") from None


def _number(value: str, field: str, default: Optional[float] = None) -> float:
    try:
        return float(value) if value else float(default)   # float(None) -> TypeError when required
    except (TypeError, ValueError):
        raise SwitchError(422, f"{field} is missing or not a number") from None


def parse_bhf_xml(xml) -> dict:
    """Map one BHF `<Claims>` message to a rails claim."""
    if not isinstance(xml, str) or not xml.strip() or len(xml) > MAX_MESSAGE:
        raise SwitchError(422, f"message must be an XML document of at most {MAX_MESSAGE} characters")
    if "<!DOCTYPE" in xml.upper() or "<!ENTITY" in xml.upper():
        raise SwitchError(422, "a DOCTYPE or ENTITY declaration is not accepted")
    try:
        root = ET.fromstring(xml.strip())
    except ET.ParseError as e:
        raise SwitchError(422, f"malformed XML: {e}") from None
    doc = root.find("Document")
    hdr = doc.find("ClaimHeader") if doc is not None else None
    if hdr is None:
        raise SwitchError(422, "the message has no <Document>/<ClaimHeader>")

    provider = _text(hdr, "BhfNumber/Treating") or _text(hdr, "BhfNumber/Supplier")
    if not provider:
        raise SwitchError(422, "the message has no practice number (<BhfNumber>/<Treating> or <Supplier>)")
    claim_id = _text(hdr, "ClaimNbr") or _text(hdr, "Account/AccountNbr")
    if not claim_id:
        raise SwitchError(422, "the message has no claim reference (<ClaimNbr> or <Account>/<AccountNbr>)")
    patient = hdr.find("Patient") if hdr.find("Patient") is not None else hdr.find("Member")
    identity = _text(patient, "IdNumber") or _text(patient, "MemberNumber")
    if not identity:
        raise SwitchError(422, "the message has no patient identity (<Patient>/<IdNumber>)")
    service = _date(_text(hdr, "Date/Service"), "service date (<Date>/<Service>)", required=True)
    dx = next((c for c in (_text(d, "Code") for d in hdr.findall("ClaimDiagnosis")) if c), "")
    discipline = _text(hdr, "Header/Discipline")

    lines = []
    for item in doc.findall("Item"):
        proc = item.find("Procedure")
        if proc is None:
            continue
        nappi = _text(item, "LineType").upper() in _NAPPI_TYPES
        code = (_text(proc, "Nappi") if nappi else "") or _text(proc, "Tariff")
        if not code:
            raise SwitchError(422, "an <Item> has no <Tariff> or <Nappi> code")
        lines.append({
            "kind": "NAPPI" if nappi else "TARIFF", "code": code,
            "qty": _number(_text(proc, "Quantity"), "<Quantity>", default=1),
            "amount": _number(_text(item, "ItemFinancials/Total"), "<ItemFinancials>/<Total>"),
            "service_date": _date(_text(item, "ServiceDate"), "<ServiceDate>") or service,
            "provider_id": provider, "dx": dx, "discipline": discipline})
    if not lines:
        raise SwitchError(422, "the message has no billable <Item>/<Procedure> lines")

    claim = {
        "claim_id": claim_id, "claim_type": "SUPPLIER", "national_id": identity,
        "accident_date": _date(_text(hdr, "AccidentDate"), "<AccidentDate>", required=True),
        "lodged_on": _date(_text(hdr, "Date/Created"), "<Date>/<Created>") or date.today().isoformat(),
        "documents": {"INVOICES": True}, "lines": lines,
        "facility": _text(hdr, "Header/PlaceOfService") in _HOSPITAL_POS,
    }
    if _text(hdr, "CaseNumber"):
        claim["case_number_raw"] = _text(hdr, "CaseNumber")
    return claim


def submit(db: Session, payload: dict, idempotency_key: Optional[str], signature: Optional[str]) -> dict:
    if not idempotency_key:
        raise SwitchError(400, "Idempotency-Key header required")
    try:
        caller, jti = rails_service.authenticate_write(db, payload, signature)
        if payload.get("format") not in FORMATS:
            raise SwitchError(422, f"format must be one of {sorted(FORMATS)}")
        claim = parse_bhf_xml(payload.get("message"))
        return rails_service.submit_as(db, caller, jti, payload, idempotency_key, claim=claim)
    except rails_service.RailsError as e:
        raise SwitchError(e.status, e.detail) from None
