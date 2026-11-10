"""Provider lookups over the rails channel (port of CIE's interface-standard profiles).

What a provider's system may ask the Fund after it has submitted a claim, and before it bills:

  claim status          where a submitted claim stands, and whether it has been paid
  registration lookup   whether the Fund holds a claim for this claimant and accident — a
                        pre-flight check before billing, which defeats billing on a claim that
                        does not exist
  objections            lodge an objection to a determination and poll its outcome; it lands in
                        the same dispute register the Fund's operators work

Disclosure is deliberately thin. A provider learns the outcome and the payment, never the risk
band, the score or a review signal, and a registration lookup answers only about the details the
provider itself supplied.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

import engine

from . import disputes_service, models
from .pseudonymise import RAW_SA_ID, token

PROVIDER_SUBJECTS = {"TARIFF", "QUANTUM", "REPUDIATION"}   # what a provider may object to
MAX_GROUNDS = 2000
_OPEN_DISPUTE = ("LODGED", "UNDER_RECONSIDERATION", "REJECTED", "REFERRED")


class ProviderError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def _latest_determination(db: Session, claim_id: str) -> Optional["models.Determination"]:
    return db.scalar(select(models.Determination).where(models.Determination.claim_id == claim_id)
                     .order_by(models.Determination.id.desc()).limit(1))


def _outcome(det: "models.Determination") -> str:
    return ("CLEAN_PASS" if det.disposition == "CLEAN"
            else "REPRICED" if det.disposition == "ADJUSTED" else "HELD")


# ── claim status ─────────────────────────────────────────────────────────────
def _payment(db: Session, claim_id: str) -> dict:
    """The latest live payment instruction for the claim, as the provider needs to see it."""
    rows = db.execute(
        select(models.PaymentInstruction, models.PaymentBatch.status)
        .join(models.PaymentBatch, models.PaymentBatch.id == models.PaymentInstruction.batch_id)
        .where(models.PaymentInstruction.claim_id == claim_id,
               models.PaymentBatch.status != "CANCELLED")
        .order_by(models.PaymentInstruction.id.desc())).all()
    if not rows:
        return {"status": "NOT_QUEUED", "amount": None, "remittances": []}
    inst, batch_status = rows[0]
    refs = sorted(set(db.scalars(
        select(models.Remittance.ref)
        .join(models.RemittanceLine, models.RemittanceLine.remittance_id == models.Remittance.id)
        .where(models.RemittanceLine.claim_id == claim_id))))
    return {"status": {"OPEN": "QUEUED", "APPROVED": "APPROVED"}.get(batch_status, "PAID"),
            "amount": inst.amount, "remittances": refs}


def claim_status(db: Session, claim_id: str) -> dict:
    claim = db.get(models.ClaimRecord, claim_id)
    det = _latest_determination(db, claim_id) if claim is not None else None
    if claim is None or det is None:
        raise ProviderError(404, "claim not found")
    lifecycle = db.get(models.ClaimLifecycle, claim_id)
    billed = engine.money(sum((engine.D(l.billed) for l in db.scalars(
        select(models.BillingLineRecord).where(models.BillingLineRecord.claim_id == claim_id))),
        engine.D(0)))
    return {
        "claimId": claim_id, "claimType": claim.claim_type,
        "receivedAt": claim.created_at.isoformat() if claim.created_at else None,
        "stage": lifecycle.stage if lifecycle is not None else None,
        "outcome": _outcome(det), "billed": billed, "payable": det.net_payable,
        "payment": _payment(db, claim_id),
        "objections": [objection_dict(db, d) for d in db.scalars(
            select(models.Dispute).where(models.Dispute.claim_id == claim_id,
                                         models.Dispute.raised_by == "PROVIDER")
            .order_by(models.Dispute.id))],
    }


# ── registration lookup ──────────────────────────────────────────────────────
def _party_token(body: dict) -> str:
    """The claimant as the Fund knows them. A raw identity number is tokenised here and is never
    stored or echoed; a ready party token passes through, but a raw number in its place is refused."""
    raw = str(body.get("national_id") or "").strip()
    tok = str(body.get("party_token") or "").strip()
    if raw:
        return token(raw, "P")
    if not tok:
        raise ProviderError(422, "national_id or party_token is required")
    if RAW_SA_ID.match(tok):
        raise ProviderError(422, "party_token looks like a raw national ID — send it as national_id")
    return tok


def _iso(value, field: str) -> Optional[date]:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        raise ProviderError(422, f"{field} must be a date (YYYY-MM-DD)") from None


def registration_lookup(db: Session, body: dict) -> dict:
    """Is there a registered claim for this claimant, and do the supplied details match it?

    `registered` is true only when a personal claim exists for the claimant AND every detail the
    provider supplied (accident date, police case number) matches one such claim. The answer names
    which supplied detail failed; it never volunteers the Fund's own values."""
    party = _party_token(body)
    accident_date = _iso(body.get("accident_date"), "accident_date")
    case_number = engine.normalise_cas(body.get("case_number")) if body.get("case_number") else None
    if body.get("case_number") and case_number is None:
        raise ProviderError(422, "case_number is not a recognisable police case number")

    claims = list(db.scalars(select(models.ClaimRecord)
                             .where(models.ClaimRecord.party_token == party,
                                    models.ClaimRecord.claim_type == "PERSONAL")
                             .order_by(models.ClaimRecord.created_at)))
    if not claims:
        return {"registered": False, "code": "NOT_REGISTERED",
                "detail": "No claim is registered for this claimant.", "checks": {}}

    def _checks(c) -> dict:
        out = {}
        if accident_date is not None:
            out["accidentDate"] = "MATCH" if c.accident_date == accident_date else "MISMATCH"
        if case_number is not None:
            raw = (c.raw or {}).get("case_number_raw")
            out["caseNumber"] = "MATCH" if engine.normalise_cas(raw) == case_number else "MISMATCH"
        return out

    scored = [(c, _checks(c)) for c in claims]
    best, checks = max(scored, key=lambda x: sum(v == "MATCH" for v in x[1].values()))
    if "MISMATCH" in checks.values():
        failed = "ACCIDENT_DATE_MISMATCH" if checks.get("accidentDate") == "MISMATCH" else "CASE_NUMBER_MISMATCH"
        return {"registered": False, "code": failed, "checks": checks,
                "detail": "A claim exists for this claimant, but a supplied detail does not match it."}
    merits = db.get(models.MeritsDetermination, best.claim_id)
    undertaking = db.scalar(select(models.Undertaking.id).where(
        models.Undertaking.claim_id == best.claim_id, models.Undertaking.status == "ACTIVE").limit(1))
    return {"registered": True, "code": "REGISTERED", "checks": checks,
            "detail": "A claim is registered for this claimant.",
            "claimRef": best.claim_id,
            "liability": merits.status if merits is not None else "PENDING",
            "undertakingActive": undertaking is not None}


# ── objections ───────────────────────────────────────────────────────────────
def objection_ref(d: "models.Dispute") -> str:
    return f"OBJ-{d.id}"


def _provider_of(d: "models.Dispute") -> str:
    return d.opened_by[len("provider:"):] if d.opened_by.startswith("provider:") else ""


def objection_dict(db: Session, d: "models.Dispute") -> dict:
    det = _latest_determination(db, d.claim_id)
    cutoff = det.created_at + timedelta(days=disputes_service.OBJECTION_WINDOW_DAYS) if det else None
    return {
        "objectionRef": objection_ref(d), "claimId": d.claim_id, "providerId": _provider_of(d),
        "subject": d.subject, "status": d.status, "channel": d.channel, "outcome": d.outcome,
        "lodgedAt": d.opened_at.isoformat() if d.opened_at else None,
        "closedAt": d.closed_at.isoformat() if d.closed_at else None,
        "late": bool(cutoff and d.opened_at and d.opened_at > cutoff),   # recorded, never refused
    }


def lodge_objection(db: Session, body: dict) -> dict:
    """Record a provider's objection in the dispute register. The provider must have billed on
    the claim; one open objection per claim and subject."""
    claim_id = str(body.get("claim_id") or "").strip()
    provider_id = str(body.get("provider_id") or "").strip()
    subject = str(body.get("subject") or "").strip().upper()
    grounds = str(body.get("grounds") or "").strip()
    if not claim_id or not provider_id:
        raise ProviderError(422, "claim_id and provider_id are required")
    if subject not in PROVIDER_SUBJECTS:
        raise ProviderError(422, f"subject must be one of {sorted(PROVIDER_SUBJECTS)}")
    if not grounds or len(grounds) > MAX_GROUNDS:
        raise ProviderError(422, f"grounds are required (at most {MAX_GROUNDS} characters)")
    billed = db.scalar(select(models.BillingLineRecord.id).where(
        models.BillingLineRecord.claim_id == claim_id,
        models.BillingLineRecord.provider_id == provider_id).limit(1))
    if billed is None:                                 # unknown claim and not-your-claim look the same
        raise ProviderError(404, "no claim with that reference was billed by this provider")
    opened_by = f"provider:{provider_id}"
    if db.scalar(select(models.Dispute.id).where(
            models.Dispute.claim_id == claim_id, models.Dispute.subject == subject,
            models.Dispute.opened_by == opened_by, models.Dispute.status.in_(_OPEN_DISPUTE)).limit(1)):
        raise ProviderError(409, "an objection on this claim and subject is already open")
    d = disputes_service.lodge(db, {"username": opened_by}, claim_id, subject, "PROVIDER", grounds)
    return objection_dict(db, d)


def _dispute_by_ref(db: Session, ref: str) -> "models.Dispute":
    num = ref[4:] if ref.startswith("OBJ-") else ""
    d = db.get(models.Dispute, int(num)) if num.isdigit() else None
    if d is None or d.raised_by != "PROVIDER":
        raise ProviderError(404, "objection not found")
    return d


def get_objection(db: Session, ref: str) -> dict:
    return objection_dict(db, _dispute_by_ref(db, ref))


def list_objections(db: Session, provider_id: str) -> list[dict]:
    return [objection_dict(db, d) for d in db.scalars(
        select(models.Dispute).where(models.Dispute.opened_by == f"provider:{provider_id}")
        .order_by(models.Dispute.id.desc()))]

