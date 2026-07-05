"""POPIA-minimal notification service (domain-logic §12.8).

Event-driven: claim lifecycle transitions emit outbound SMS/e-mail from POPIA-minimal templates —
the claim reference (R_*) plus what's outstanding and how to submit, and NEVER medical or quantum
detail. Delivery (SMS/e-mail) is an external integration; this module is the per-claim outbox +
delivery log. Sending is opt-in: a notification is SUPPRESSED unless the pseudonymous party has
opted in to a channel. The actual contact detail (phone/e-mail, PII) is resolved externally at
delivery — it is never stored here.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from . import models

CHANNELS = {"SMS", "EMAIL", "NONE"}

# Templates keyed by the lifecycle stage reached. Only claimant-facing events have one; internal
# stages (MERITS, QUANTUM, LITIGATION, COURT_ORDER) are intentionally silent. POPIA-minimal:
# claim reference + action, never a name, an amount, or a diagnosis.
TEMPLATES = {
    "VALIDATED":           "Claim {claim}: lodgement validated — no action needed.",
    "REJECTED_COMPLIANCE": "Claim {claim}: rejected on lodgement compliance. See the RAF portal for what is outstanding.",
    "REPUDIATED":          "Claim {claim}: not accepted. You may lodge an objection within the objection window via the RAF portal.",
    "OFFER_MADE":          "Claim {claim}: an offer is available — please review and respond via the RAF portal.",
    "SETTLED":             "Claim {claim}: settled.",
    "PAID":                "Claim {claim}: payment has been processed.",
    "FINALIZED":           "Claim {claim}: finalised.",
}


def emit(db: Session, event: str, claim_id: str, detail: str = "") -> Optional["models.Notification"]:
    """Enqueue a POPIA-minimal notification for a claim event (no commit — rides the caller's
    transaction, so a rolled-back transition emits nothing). Events without a template are ignored;
    a party who hasn't opted in gets a SUPPRESSED (logged, undelivered) record."""
    tmpl = TEMPLATES.get(event)
    if tmpl is None:
        return None
    claim = db.get(models.ClaimRecord, claim_id)
    party = claim.party_token if claim else None
    pref = db.get(models.NotificationPref, party) if party else None
    if pref is not None and pref.opted_in and pref.channel != "NONE":
        channel, status = pref.channel, "PENDING"
    else:
        channel, status = (pref.channel if pref else "NONE"), "SUPPRESSED"
    n = models.Notification(claim_id=claim_id, party_token=party, channel=channel, event=event,
                            body=tmpl.format(claim=claim_id, detail=detail), status=status)
    db.add(n)
    return n


# ── opt-in channel preference on the (pseudonymous) party record ──────────────
def set_pref(db: Session, party_token: str, channel: str, opted_in: bool) -> dict:
    if channel not in CHANNELS:
        raise ValueError(f"invalid channel: {channel} (SMS | EMAIL | NONE)")
    p = db.get(models.NotificationPref, party_token)
    if p is not None:
        p.channel, p.opted_in = channel, bool(opted_in)
    else:
        db.add(models.NotificationPref(party_token=party_token, channel=channel, opted_in=bool(opted_in)))
    db.commit()
    return {"party_token": party_token, "channel": channel, "opted_in": bool(opted_in)}


def get_pref(db: Session, party_token: str) -> Optional[dict]:
    p = db.get(models.NotificationPref, party_token)
    return {"party_token": p.party_token, "channel": p.channel, "opted_in": p.opted_in} if p else None


# ── outbox + delivery log ─────────────────────────────────────────────────────
def _dict(n: "models.Notification") -> dict:
    return {"id": n.id, "claim_id": n.claim_id, "party_token": n.party_token, "channel": n.channel,
            "event": n.event, "body": n.body, "status": n.status,
            "created_at": n.created_at.isoformat() if n.created_at else None,
            "sent_at": n.sent_at.isoformat() if n.sent_at else None}


def outbox(db: Session, status: Optional[str] = None, claim_id: Optional[str] = None,
           limit: int = 200) -> list[dict]:
    stmt = select(models.Notification).order_by(desc(models.Notification.id))
    if status:
        stmt = stmt.where(models.Notification.status == status)
    if claim_id:
        stmt = stmt.where(models.Notification.claim_id == claim_id)
    return [_dict(n) for n in db.scalars(stmt.limit(limit))]


def _set_status(db: Session, notif_id: int, status: str, stamp: bool) -> dict:
    n = db.get(models.Notification, notif_id)
    if n is None:
        raise ValueError(f"no such notification: {notif_id}")
    n.status = status
    if stamp:
        n.sent_at = datetime.now()
    db.commit()
    return _dict(n)


def mark_sent(db: Session, notif_id: int) -> dict:
    """Delivery-worker (or interim manual-send) callback: PENDING -> SENT."""
    return _set_status(db, notif_id, "SENT", stamp=True)


def mark_failed(db: Session, notif_id: int) -> dict:
    return _set_status(db, notif_id, "FAILED", stamp=False)
