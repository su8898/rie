"""Remittance advice — the Fund's payment record to a provider (port of CIE's ERA).

When a payment batch is paid, each provider paid in it gets ONE remittance advice: every
adjudicated line on the claims paid, with billed / paid / reduced and the reason for a reduction.
Lines come from the stored adjudication (nothing is re-priced here) and are reconciled to the
amount ACTUALLY paid on the claim, so the advice never contradicts the payment instruction.

Formats: JSON for the provider's system, a `<Remittance>` XML document, and a print-ready page.
Only provider-facing instructions remit (SUPPLIER, UNDERTAKING_INVOICE); settlements, court
orders and interim payments go to claimants and are not remittances.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Optional
from xml.sax.saxutils import escape, quoteattr

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from engine.vocab import D, money

from .clock import utcnow
from . import models

PROVIDER_SOURCES = {"SUPPLIER", "UNDERTAKING_INVOICE"}
PAYMENT_ADJUSTED = "PAYMENT_ADJUSTED"

# What a provider is told about a reduced line. Only payment-rule reasons appear — a review or
# fraud signal on a claim is never disclosed on a remittance.
REASON_TEXT = {
    "BILLED_OVER_REFERENCE": "Repriced to the reference tariff",
    "DUPLICATE_LINE": "Duplicate line: the first occurrence is paid",
    "SUPPLIER_PRECLUSION": "Already paid on another claim",
    "UNBUNDLING_CONFLICT": "The tariff limits this code to once per encounter",
    "PREAUTH_EXCEEDED": "Above the authorised quantity or amount",
    "PREAUTH_MISSING": "Pre-authorisation required and not found",
    "SERVICE_BEFORE_ACCIDENT": "Service date is before the accident",
    "UNDERTAKING_NOT_ACTIVE": "No active undertaking",
    "UNDERTAKING_SCOPE": "Outside the scope of the undertaking",
    PAYMENT_ADJUSTED: "Apportioned, or net of an earlier payment",
}


class RemittanceError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def _new_ref(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10].upper()}"


def allocate(payables: list[float], amount: float) -> list[float]:
    """Spread the amount actually paid on a claim over its lines, pro rata to each line's
    adjudicated payable, to the cent. Rounding residue (or the whole amount, if nothing was
    payable) lands on the last line, so the lines always sum to the payment."""
    if not payables:
        return []
    total, amt = sum((D(p) for p in payables), Decimal(0)), D(amount)
    paid = [D(money(D(p) * amt / total)) if total > 0 else Decimal(0) for p in payables]
    paid[-1] += amt - sum(paid, Decimal(0))
    return [money(max(x, Decimal(0))) for x in paid]


def _disclosed(reasons: list, adjusted: bool, reduced: float) -> list[str]:
    if reduced <= 0:
        return []
    out = [r for r in reasons or [] if r in REASON_TEXT]
    return out + [PAYMENT_ADJUSTED] if adjusted else out


def issue_for_batch(db: Session, batch: "models.PaymentBatch", user: dict) -> list["models.Remittance"]:
    """Issue the remittance advice for each provider paid in a PAID batch. Idempotent: a provider
    that already has one for this batch is skipped. The caller commits."""
    if batch.status != "PAID":
        raise RemittanceError(409, "remittance advice is issued once the batch is paid")
    have = set(db.scalars(select(models.Remittance.provider_id)
                          .where(models.Remittance.batch_id == batch.id)))
    by_provider: dict[str, list[dict]] = {}
    for inst in db.scalars(select(models.PaymentInstruction)
                           .where(models.PaymentInstruction.batch_id == batch.id,
                                  models.PaymentInstruction.paid.is_(True),
                                  models.PaymentInstruction.source.in_(PROVIDER_SOURCES))
                           .order_by(models.PaymentInstruction.id)):
        lines = list(db.scalars(select(models.BillingLineRecord)
                                .where(models.BillingLineRecord.claim_id == inst.claim_id)
                                .order_by(models.BillingLineRecord.id)))
        claim = db.get(models.ClaimRecord, inst.claim_id)
        paid = allocate([l.payable for l in lines], inst.amount)
        for line, line_paid in zip(lines, paid):
            reduced = money(D(line.billed) - D(line_paid))
            by_provider.setdefault(line.provider_id, []).append({
                "claim_id": inst.claim_id, "party_token": claim.party_token, "kind": line.kind,
                "code": line.code, "service_date": line.service_date, "billed": line.billed,
                "paid": line_paid, "reduced": reduced,
                "reasons": _disclosed(line.reasons, line_paid != line.payable, reduced)})
    issued = []
    for provider_id, rows in by_provider.items():
        if provider_id in have:
            continue
        dates = [r["service_date"] for r in rows if r["service_date"]]
        rem = models.Remittance(
            ref=_new_ref("ERA"), invoice_ref=_new_ref("INV"), payment_ref=f"BATCH-{batch.id}",
            batch_id=batch.id, provider_id=provider_id,
            period_from=min(dates) if dates else None, period_to=max(dates) if dates else None,
            n_claims=len({r["claim_id"] for r in rows}),
            total_billed=money(sum((D(r["billed"]) for r in rows), Decimal(0))),
            total_paid=money(sum((D(r["paid"]) for r in rows), Decimal(0))),
            total_reduced=money(sum((D(r["reduced"]) for r in rows), Decimal(0))),
            status="REMITTED", issued_by=user["username"])
        db.add(rem)
        db.flush()
        db.add_all(models.RemittanceLine(remittance_id=rem.id, **r) for r in rows)
        issued.append(rem)
    return issued


def issue(db: Session, batch_id: int, user: dict) -> list[dict]:
    """Operator re-issue for a batch paid before remittances existed (or never issued)."""
    batch = db.get(models.PaymentBatch, batch_id)
    if batch is None:
        raise RemittanceError(404, "no such payment batch")
    out = [summary(r) for r in issue_for_batch(db, batch, user)]
    db.commit()
    return out


def summary(r: "models.Remittance") -> dict:
    return {
        "ref": r.ref, "invoice_ref": r.invoice_ref, "payment_ref": r.payment_ref,
        "batch_id": r.batch_id, "provider_id": r.provider_id,
        "period_from": r.period_from.isoformat() if r.period_from else None,
        "period_to": r.period_to.isoformat() if r.period_to else None,
        "n_claims": r.n_claims, "total_billed": r.total_billed, "total_paid": r.total_paid,
        "total_reduced": r.total_reduced, "status": r.status,
        "issued_at": r.created_at.isoformat() if r.created_at else None,
        "acknowledged_at": r.acknowledged_at.isoformat() if r.acknowledged_at else None,
    }


def _by_ref(db: Session, ref: str) -> "models.Remittance":
    r = db.scalar(select(models.Remittance).where(models.Remittance.ref == ref))
    if r is None:
        raise RemittanceError(404, "remittance not found")
    return r


def detail(db: Session, ref: str) -> dict:
    """The full advice: the summary plus its claims, each with its lines and totals."""
    r = _by_ref(db, ref)
    claims: dict[str, dict] = {}
    for l in db.scalars(select(models.RemittanceLine)
                        .where(models.RemittanceLine.remittance_id == r.id)
                        .order_by(models.RemittanceLine.id)):
        c = claims.setdefault(l.claim_id, {"claim_id": l.claim_id, "patient": l.party_token,
                                           "billed": Decimal(0), "paid": Decimal(0), "lines": []})
        c["billed"] += D(l.billed)
        c["paid"] += D(l.paid)
        c["lines"].append({
            "kind": l.kind, "code": l.code,
            "service_date": l.service_date.isoformat() if l.service_date else None,
            "billed": l.billed, "paid": l.paid, "reduced": l.reduced, "reasons": list(l.reasons or []),
            "reason_text": "; ".join(REASON_TEXT[x] for x in l.reasons or [])})
    for c in claims.values():
        c["reduced"] = money(c["billed"] - c["paid"])
        c["billed"], c["paid"] = money(c["billed"]), money(c["paid"])
        c["outcome"] = "REDUCED" if c["reduced"] > 0 else "PAID_IN_FULL"
    return {**summary(r), "claims": list(claims.values())}


def list_remittances(db: Session, provider_id: Optional[str] = None,
                     date_from: Optional[date] = None, date_to: Optional[date] = None,
                     limit: int = 200) -> list[dict]:
    """Newest first. The period filter matches advices whose service dates overlap it."""
    stmt = select(models.Remittance).order_by(models.Remittance.id.desc()).limit(limit)
    if provider_id:
        stmt = stmt.where(models.Remittance.provider_id == provider_id)
    if date_from:
        stmt = stmt.where(models.Remittance.period_to >= date_from)
    if date_to:
        stmt = stmt.where(models.Remittance.period_from <= date_to)
    return [summary(r) for r in db.scalars(stmt)]


def search(db: Session, *, provider_id: Optional[str] = None, status: Optional[str] = None,
           batch_id: Optional[int] = None, q: Optional[str] = None,
           date_from: Optional[date] = None, date_to: Optional[date] = None,
           limit: int = 25, offset: int = 0) -> tuple[list[dict], int]:
    """The operator's remittance worklist: newest first, filtered, with a total for paging.
    `q` matches the advice reference, the practice number or a claim on the advice."""
    stmt = select(models.Remittance)
    if provider_id:
        stmt = stmt.where(models.Remittance.provider_id == provider_id)
    if status:
        stmt = stmt.where(models.Remittance.status == status)
    if batch_id is not None:
        stmt = stmt.where(models.Remittance.batch_id == batch_id)
    if date_from:
        stmt = stmt.where(models.Remittance.period_to >= date_from)
    if date_to:
        stmt = stmt.where(models.Remittance.period_from <= date_to)
    if q and (q := q.strip()):
        like = f"%{q}%"
        on_advice = select(models.RemittanceLine.remittance_id).where(models.RemittanceLine.claim_id.ilike(like))
        stmt = stmt.where(or_(models.Remittance.ref.ilike(like), models.Remittance.provider_id.ilike(like),
                              models.Remittance.id.in_(on_advice)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(models.Remittance.id.desc()).limit(limit).offset(offset))
    return [summary(r) for r in rows], total


def acknowledge(db: Session, ref: str) -> dict:
    """The provider's system confirms it received and reconciled the advice. Idempotent."""
    r = _by_ref(db, ref)
    if r.status != "ACKNOWLEDGED":
        r.status, r.acknowledged_at = "ACKNOWLEDGED", utcnow()
        db.commit()
    return summary(r)


# ── wire format: <Remittance> XML ────────────────────────────────────────────
def to_xml(d: dict) -> str:
    def a(v) -> str:
        return quoteattr(str(v if v is not None else ""))

    claims = ""
    for c in d["claims"]:
        lines = "".join(
            f'<Line kind={a(l["kind"])} code={a(l["code"])} serviceDate={a(l["service_date"])}>'
            f'<Billed>{l["billed"]:.2f}</Billed><Paid>{l["paid"]:.2f}</Paid>'
            f'<Reduced>{l["reduced"]:.2f}</Reduced>'
            + "".join(f'<Reason code={a(x)}>{escape(REASON_TEXT[x])}</Reason>' for x in l["reasons"])
            + "</Line>" for l in c["lines"])
        claims += (f'<Claim ref={a(c["claim_id"])} patient={a(c["patient"])} outcome={a(c["outcome"])}>'
                   f'{lines}<ClaimTotals><Billed>{c["billed"]:.2f}</Billed><Paid>{c["paid"]:.2f}</Paid>'
                   f'<Reduced>{c["reduced"]:.2f}</Reduced></ClaimTotals></Claim>')
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<Remittance>'
            f'<Header><RemittanceRef>{escape(d["ref"])}</RemittanceRef>'
            f'<InvoiceRef>{escape(d["invoice_ref"])}</InvoiceRef>'
            f'<PaymentRef>{escape(d["payment_ref"])}</PaymentRef>'
            f'<Provider>{escape(d["provider_id"])}</Provider>'
            f'<Period><From>{d["period_from"] or ""}</From><To>{d["period_to"] or ""}</To></Period>'
            f'<Status>{escape(d["status"])}</Status></Header>'
            f'<Claims>{claims}</Claims>'
            f'<Totals><Claims>{d["n_claims"]}</Claims><Billed>{d["total_billed"]:.2f}</Billed>'
            f'<Paid>{d["total_paid"]:.2f}</Paid><Reduced>{d["total_reduced"]:.2f}</Reduced></Totals>'
            '</Remittance>')


# ── print format ─────────────────────────────────────────────────────────────
def _rand(x) -> str:
    return "R" + f"{float(x or 0):,.2f}".replace(",", " ")


def print_html(d: dict) -> str:
    """A print-ready remittance advice. Every value is escaped; nothing here is executable."""
    rows = ""
    for c in d["claims"]:
        rows += (f'<tr class="clm"><td colspan="3"><b>{escape(c["claim_id"])}</b> · '
                 f'{escape(c["patient"])}</td><td class="n">{_rand(c["billed"])}</td>'
                 f'<td class="n">{_rand(c["paid"])}</td><td class="n">{_rand(c["reduced"])}</td></tr>')
        for l in c["lines"]:
            why = (f'<span class="red">{_rand(l["reduced"])}: {escape(l["reason_text"])}</span>'
                   if l["reduced"] > 0 else "")
            rows += (f'<tr class="ln"><td>{escape(l["code"])}</td><td>{escape(l["kind"])}</td>'
                     f'<td>{escape(l["service_date"] or "")}</td><td class="n">{_rand(l["billed"])}</td>'
                     f'<td class="n">{_rand(l["paid"])}</td><td class="n">{why}</td></tr>')
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Remittance {escape(d["ref"])}</title>
<style>
 body{{font:13px/1.5 -apple-system,Segoe UI,sans-serif;color:#1a1a1a;max-width:860px;margin:24px auto;padding:0 16px}}
 h1{{font-size:19px;margin:0 0 2px}} .sub{{color:#5b6b76;margin-bottom:14px}}
 .kv{{display:grid;grid-template-columns:170px 1fr;gap:2px 12px;margin:10px 0 16px}} .kv b{{color:#5b6b76;font-weight:500}}
 table{{width:100%;border-collapse:collapse;font-size:12px}} th,td{{text-align:left;padding:5px 8px;border-bottom:1px solid #eef2f5}}
 th{{font-size:10px;text-transform:uppercase;letter-spacing:.4px;color:#5b6b76}}
 td.n,th.n{{text-align:right;font-variant-numeric:tabular-nums}} tr.clm td{{background:#f4f7f9;border-top:1px solid #dce4ea}}
 tr.ln td:first-child{{padding-left:20px;color:#5b6b76}} .red{{color:#c2410c;font-weight:600}}
 .tot{{margin-top:14px;text-align:right;font-size:14px}}
 .note{{margin-top:18px;font-size:11px;color:#5b6b76;border-top:1px solid #dce4ea;padding-top:8px}}
 @media print{{body{{margin:0}}}}
</style></head><body>
<h1>Remittance advice</h1>
<div class="sub">Road Accident Fund · medical accounts</div>
<div class="kv">
  <b>Remittance reference</b><span>{escape(d["ref"])}</span>
  <b>Invoice reference</b><span>{escape(d["invoice_ref"])}</span>
  <b>Payment reference</b><span>{escape(d["payment_ref"])}</span>
  <b>Provider</b><span>{escape(d["provider_id"])}</span>
  <b>Service period</b><span>{escape(d["period_from"] or "—")} to {escape(d["period_to"] or "—")}</span>
  <b>Claims remitted</b><span>{d["n_claims"]}</span>
</div>
<table><thead><tr><th>Code</th><th>Type</th><th>Service date</th><th class="n">Billed</th><th class="n">Paid</th><th class="n">Reduced</th></tr></thead>
<tbody>{rows}</tbody></table>
<div class="tot">Billed {_rand(d["total_billed"])} &nbsp;·&nbsp; Reduced <span class="red">{_rand(d["total_reduced"])}</span> &nbsp;·&nbsp; <b>Paid {_rand(d["total_paid"])}</b></div>
<div class="note">Each reduction carries its reason. A provider may lodge an objection to a reduction within 180 days of this advice.</div>
</body></html>"""
