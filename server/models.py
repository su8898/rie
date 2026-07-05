"""ORM — reference (loader-populated), corpus (immutable), operational.

Kept deliberately close to the engine's determination record so persistence is a thin write.
JSON columns hold the pseudonymised claim payload, reason lists, holds, and accident graph fields.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


# ── auth ─────────────────────────────────────────────────────────────────────
class AppUser(Base):
    __tablename__ = "app_users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String)
    active: Mapped[bool] = mapped_column(default=True)


# ── reference (effective-dated, loader-populated) ────────────────────────────
class RefRpl(Base):
    __tablename__ = "ref_rpl"
    code: Mapped[str] = mapped_column(String, primary_key=True)
    gp: Mapped[float] = mapped_column(Float)
    spec: Mapped[Optional[float]] = mapped_column(Float, nullable=True)


class RefNegotiated(Base):
    __tablename__ = "ref_negotiated"
    kind: Mapped[str] = mapped_column(String, primary_key=True)
    code: Mapped[str] = mapped_column(String, primary_key=True)
    rate: Mapped[float] = mapped_column(Float)


class RefRaf2022(Base):
    __tablename__ = "ref_raf2022"
    code: Mapped[str] = mapped_column(String, primary_key=True)
    rate: Mapped[float] = mapped_column(Float)


class RefEmpirical(Base):
    __tablename__ = "ref_empirical"
    kind: Mapped[str] = mapped_column(String, primary_key=True)
    code: Mapped[str] = mapped_column(String, primary_key=True)
    median: Mapped[float] = mapped_column(Float)


class RefNappiSep(Base):
    __tablename__ = "ref_nappi_sep"
    nappi_code: Mapped[str] = mapped_column(String, primary_key=True)
    sep: Mapped[float] = mapped_column(Float)


class RefNonBench(Base):
    __tablename__ = "ref_non_bench"
    code: Mapped[str] = mapped_column(String, primary_key=True)


class RefCap(Base):
    __tablename__ = "ref_cap"
    effective_from: Mapped[date] = mapped_column(Date, primary_key=True)
    annual_cap: Mapped[float] = mapped_column(Float)


class RefPreauth(Base):
    __tablename__ = "ref_preauth"
    code: Mapped[str] = mapped_column(String, primary_key=True)


class RefIcd10(Base):
    __tablename__ = "ref_icd10"
    code: Mapped[str] = mapped_column(String, primary_key=True)
    description: Mapped[str] = mapped_column(String, default="")
    code3_desc: Mapped[str] = mapped_column(String, default="")
    chapter_desc: Mapped[str] = mapped_column(String, default="")
    valid_primary: Mapped[bool] = mapped_column(default=True)
    valid_clinical: Mapped[bool] = mapped_column(default=True)


class RefEdition(Base):
    """Provenance of loaded reference editions (from reference.db ref_meta)."""
    __tablename__ = "ref_edition"
    kind: Mapped[str] = mapped_column(String, primary_key=True)
    version: Mapped[str] = mapped_column(String, default="")
    n: Mapped[int] = mapped_column(Integer, default=0)
    synced_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)


# ── corpus + operational ─────────────────────────────────────────────────────
class AccidentRecord(Base):
    __tablename__ = "accidents"
    accident_id: Mapped[str] = mapped_column(String, primary_key=True)
    case_number: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    when_: Mapped[date] = mapped_column("when", Date)
    where_: Mapped[str] = mapped_column("where", String, default="")
    vehicles: Mapped[list] = mapped_column(JSON, default=list)
    parties: Mapped[list] = mapped_column(JSON, default=list)
    oar_occupants: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sources: Mapped[dict] = mapped_column(JSON, default=dict)
    claims: Mapped[list] = mapped_column(JSON, default=list)


class ClaimRecord(Base):
    __tablename__ = "claims"
    claim_id: Mapped[str] = mapped_column(String, primary_key=True)
    claim_type: Mapped[str] = mapped_column(String, index=True)
    party_token: Mapped[str] = mapped_column(String, index=True)
    accident_date: Mapped[date] = mapped_column(Date)
    lodged_on: Mapped[date] = mapped_column(Date)
    raw: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class BillingLineRecord(Base):
    __tablename__ = "billing_lines"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    claim_id: Mapped[str] = mapped_column(ForeignKey("claims.claim_id"), index=True)
    provider_id: Mapped[str] = mapped_column(String, default="", index=True)
    kind: Mapped[str] = mapped_column(String)
    code: Mapped[str] = mapped_column(String)
    billed: Mapped[float] = mapped_column(Float)
    reference: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    payable: Mapped[float] = mapped_column(Float)
    src: Mapped[str] = mapped_column(String)
    legal_status: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    needs_review: Mapped[bool] = mapped_column(default=False)
    reasons: Mapped[list] = mapped_column(JSON, default=list)


class Determination(Base):
    __tablename__ = "determinations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    claim_id: Mapped[str] = mapped_column(ForeignKey("claims.claim_id"), index=True)
    accident_id: Mapped[str] = mapped_column(String, index=True)
    accident_action: Mapped[str] = mapped_column(String)
    band: Mapped[str] = mapped_column(String, index=True)
    score: Mapped[int] = mapped_column(Integer)
    disposition: Mapped[str] = mapped_column(String, index=True)
    validated: Mapped[bool] = mapped_column(default=False)
    convergence: Mapped[float] = mapped_column(Float)
    medical_payable: Mapped[float] = mapped_column(Float)
    net_payable: Mapped[float] = mapped_column(Float)
    eligible_to_pay: Mapped[bool] = mapped_column(default=False)
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    shadow_signals: Mapped[list] = mapped_column(JSON, default=list)
    holds: Mapped[list] = mapped_column(JSON, default=list)
    engine_version: Mapped[str] = mapped_column(String)
    ruleset_effective: Mapped[str] = mapped_column(String)
    reference_edition: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ── state machines (operational, actor-stamped) ──────────────────────────────
class TransitionLog(Base):
    """One append-only row per state transition across every machine (the v_determinations idea)."""
    __tablename__ = "transition_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String, index=True)
    entity_id: Mapped[str] = mapped_column(String, index=True)
    from_state: Mapped[str] = mapped_column(String)
    to_state: Mapped[str] = mapped_column(String)
    action: Mapped[str] = mapped_column(String)
    actor: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String)
    at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


class ClaimLifecycle(Base):
    __tablename__ = "claim_lifecycle"
    claim_id: Mapped[str] = mapped_column(ForeignKey("claims.claim_id"), primary_key=True)
    stage: Mapped[str] = mapped_column(String, default="LODGED", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class MeritsDetermination(Base):
    __tablename__ = "merits_determination"
    claim_id: Mapped[str] = mapped_column(ForeignKey("claims.claim_id"), primary_key=True)
    status: Mapped[str] = mapped_column(String, default="PENDING", index=True)
    fault_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ground: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class SeriousInjury(Base):
    __tablename__ = "serious_injury"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    claim_id: Mapped[str] = mapped_column(ForeignKey("claims.claim_id"), index=True)
    status: Mapped[str] = mapped_column(String, default="SUBMITTED", index=True)
    list_match: Mapped[bool] = mapped_column(default=False)
    wpi: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    narrative: Mapped[bool] = mapped_column(default=False)


class Undertaking(Base):
    __tablename__ = "undertakings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    claim_id: Mapped[str] = mapped_column(ForeignKey("claims.claim_id"), index=True)
    origin: Mapped[str] = mapped_column(String)                 # SETTLEMENT | EMERGENCY
    status: Mapped[str] = mapped_column(String, default="ISSUED", index=True)
    scope_dx: Mapped[list] = mapped_column(JSON, default=list)


class UndertakingInvoice(Base):
    __tablename__ = "undertaking_invoices"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    undertaking_id: Mapped[int] = mapped_column(ForeignKey("undertakings.id"), index=True)
    status: Mapped[str] = mapped_column(String, default="RECEIVED", index=True)
    billed: Mapped[float] = mapped_column(Float, default=0.0)
    payable: Mapped[float] = mapped_column(Float, default=0.0)
    reasons: Mapped[list] = mapped_column(JSON, default=list)


class Litigation(Base):
    __tablename__ = "litigation"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    claim_id: Mapped[str] = mapped_column(ForeignKey("claims.claim_id"), index=True)
    status: Mapped[str] = mapped_column(String, default="SUMMONS_SERVED", index=True)
    default_judgment: Mapped[bool] = mapped_column(default=False)


class Offer(Base):
    __tablename__ = "offers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    claim_id: Mapped[str] = mapped_column(ForeignKey("claims.claim_id"), index=True)
    status: Mapped[str] = mapped_column(String, default="ASSEMBLED", index=True)  # ASSEMBLED | HELD
    total: Mapped[float] = mapped_column(Float, default=0.0)
    gated_by: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class OfferHead(Base):
    __tablename__ = "offer_heads"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    offer_id: Mapped[int] = mapped_column(ForeignKey("offers.id"), index=True)
    head: Mapped[str] = mapped_column(String)
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


# ── payments (segregation of duties: assembler != approver) ──────────────────
class PaymentBatch(Base):
    __tablename__ = "payment_batch"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[str] = mapped_column(String, default="OPEN", index=True)  # OPEN|APPROVED|PAID|CANCELLED
    created_by: Mapped[str] = mapped_column(String)
    approved_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    paid_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    note: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class PaymentInstruction(Base):
    __tablename__ = "payment_instruction"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("payment_batch.id"), index=True)
    claim_id: Mapped[str] = mapped_column(ForeignKey("claims.claim_id"), index=True)
    source: Mapped[str] = mapped_column(String)   # SETTLEMENT|COURT_ORDER|UNDERTAKING_INVOICE|SUPPLIER|INTERIM
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    paid: Mapped[bool] = mapped_column(default=False)


class RailsSubmission(Base):
    """A provider->fund rails submission: the signed verdict + receipt, idempotency-keyed."""
    __tablename__ = "rails_submission"
    submission_id: Mapped[str] = mapped_column(String, primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String, index=True)
    body_hash: Mapped[str] = mapped_column(String)
    claim_id: Mapped[str] = mapped_column(String, index=True)
    outcome: Mapped[str] = mapped_column(String)
    verdict: Mapped[dict] = mapped_column(JSON)
    receipt: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class RailsSeenJti(Base):
    """Replay guard — each request's one-time JWS nonce is recorded once."""
    __tablename__ = "rails_seen_jti"
    jti: Mapped[str] = mapped_column(String, primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AuditQueue(Base):
    """Post-payment clawback recovery queue (§8e): OPEN -> UNDER_REVIEW -> RECOVERED / CLEARED."""
    __tablename__ = "audit_queue"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    claim_id: Mapped[str] = mapped_column(ForeignKey("claims.claim_id"), index=True)
    status: Mapped[str] = mapped_column(String, default="OPEN", index=True)
    reason: Mapped[str] = mapped_column(String)
    amount_at_stake: Mapped[float] = mapped_column(Float, default=0.0)
    amount_recovered: Mapped[float] = mapped_column(Float, default=0.0)
    recovery_outcome: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    assigned_to: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    opened_by: Mapped[str] = mapped_column(String)
    opened_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class PaymentEvent(Base):
    """Append-only money-audit log (§8e) — one row per created/instruction/approved/paid/cancelled."""
    __tablename__ = "payment_event"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("payment_batch.id"), index=True)
    event: Mapped[str] = mapped_column(String)
    actor: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String)
    amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
