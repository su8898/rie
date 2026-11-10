"""ORM — reference (loader-populated), corpus (immutable), operational.

Kept deliberately close to the engine's determination record so persistence is a thin write.
JSON columns hold the pseudonymised claim payload, reason lists, holds, and accident graph fields.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (JSON, Date, DateTime, Float, ForeignKey, Integer, String,
                        UniqueConstraint, func, select)
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


class AdminAudit(Base):
    """Append-only admin action log — CUD logging (SPECIFICATION §9, domain-logic §11)."""
    __tablename__ = "admin_audit"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor: Mapped[str] = mapped_column(String, index=True)
    action: Mapped[str] = mapped_column(String, index=True)
    target: Mapped[str] = mapped_column(String, default="")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ── reference (effective-dated, loader-populated) ────────────────────────────
class RefRpl(Base):
    __tablename__ = "ref_rpl"
    code: Mapped[str] = mapped_column(String, primary_key=True)      # normalised tariff code
    discipline: Mapped[str] = mapped_column(String, primary_key=True)
    rate: Mapped[float] = mapped_column(Float)


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


class RefRateVersion(Base):
    """Dated versions of a payment-rule reference rate (ported from CIE's tariff_specialty_rate).

    Append-only: a new rate for a later date SUPERSEDES the prior version (closes its
    effective_to the day before) and the old amount stays on the books, so a claim prices at the
    rate in force on its SERVICE date. `source` names the reference tier — RPL (tariff x
    discipline), NEGOTIATED (kind x code) or SEP (NAPPI single exit price). A key with versions is
    priced from them; a key without any keeps its undated row in ref_rpl / ref_negotiated /
    ref_nappi_sep. Every change is written to ref_rate_log."""
    __tablename__ = "ref_rate_version"
    __table_args__ = (UniqueConstraint("source", "kind", "code", "discipline", "effective_from",
                                       name="uq_ref_rate_version_key_from"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String, index=True)          # RPL | NEGOTIATED | SEP
    kind: Mapped[str] = mapped_column(String)                        # TARIFF | NAPPI
    code: Mapped[str] = mapped_column(String, index=True)            # normalised for TARIFF
    discipline: Mapped[str] = mapped_column(String, default="")      # RPL only
    rate: Mapped[float] = mapped_column(Float)
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)   # NULL = open
    origin: Mapped[str] = mapped_column(String, default="manual")    # baseline | manual | import
    note: Mapped[str] = mapped_column(String, default="")
    created_by: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class RefRateLog(Base):
    """Immutable rate change trail: which rate changed, when, by whom, old -> new, and why.
    Key columns are denormalised so the trail reads on its own."""
    __tablename__ = "ref_rate_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rate_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    source: Mapped[str] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String)
    code: Mapped[str] = mapped_column(String, index=True)
    discipline: Mapped[str] = mapped_column(String, default="")
    action: Mapped[str] = mapped_column(String)                      # CREATE | SUPERSEDE | RETIRE | ADJUST
    old_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    new_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    old_effective_from: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    new_effective_from: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    changed_by: Mapped[str] = mapped_column(String, default="")
    note: Mapped[str] = mapped_column(String, default="")
    changed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class RefNonBench(Base):
    __tablename__ = "ref_non_bench"
    code: Mapped[str] = mapped_column(String, primary_key=True)


class RefCodeRule(Base):
    """A tariff code's own billing rule (domain-logic §3b), ported from CIE's coding rules: a
    once-per-encounter limit, a time-modifier ladder, or a percentage-of-time modifier. One rule
    per (normalised) TARIFF code; the engine reads them through RefBook.code_rules."""
    __tablename__ = "ref_code_rule"
    code: Mapped[str] = mapped_column(String, primary_key=True)      # normalised TARIFF code
    rule: Mapped[str] = mapped_column(String)                        # engine.CODE_RULES
    param: Mapped[float] = mapped_column(Float, default=0.0)         # block minutes / share of time
    basis: Mapped[str] = mapped_column(String, default="")           # the tariff clause or guideline cited
    origin: Mapped[str] = mapped_column(String, default="manual")    # tariff | standard | manual
    created_by: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


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


class RefCpi(Base):
    """Headline CPI index (annual), for inflation-adjusting comparable awards to current rand (§5d)."""
    __tablename__ = "ref_cpi"
    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    index: Mapped[float] = mapped_column(Float)


class RefComparableAward(Base):
    """General-damages quantum authorities (§5d) — one row per reported award, LEGAL-curated.
    Bands are COMPUTED (CPI-adjusted p25–p75), never hand-set; guidance only (ENDOGENOUS-equivalent)."""
    __tablename__ = "ref_comparable_award"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    injury_class: Mapped[str] = mapped_column(String, index=True)
    severity_tier: Mapped[str] = mapped_column(String, default="")
    award_rand: Mapped[float] = mapped_column(Float)              # in the award-year's rand
    award_date: Mapped[date] = mapped_column(Date)
    citation: Mapped[str] = mapped_column(String)
    court: Mapped[str] = mapped_column(String, default="")
    notes: Mapped[str] = mapped_column(String, default="")


class RefSignalMode(Base):
    """ADMIN override of a signal's scoring mode (§11) — reference data, effective-dated and
    audit-logged, never a code deploy. An absent code falls back to the engine default (derived
    from maturity: UNVALIDATED -> SHADOW, else SCORED)."""
    __tablename__ = "ref_signal_mode"
    code: Mapped[str] = mapped_column(String, primary_key=True)
    mode: Mapped[str] = mapped_column(String)          # SHADOW | ADVISORY | SCORED
    effective_from: Mapped[date] = mapped_column(Date)
    set_by: Mapped[str] = mapped_column(String)
    note: Mapped[str] = mapped_column(String, default="")


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
    service_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)   # pay-once ledger key (§4e)


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
    needs_review: Mapped[bool] = mapped_column(default=False)          # a line needs R&N review (§3)
    advisory_signals: Mapped[list] = mapped_column(JSON, default=list) # visible, non-dispositive (§11)
    accident_candidate: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # WORKLIST match (§6.0)
    engine_version: Mapped[str] = mapped_column(String)
    ruleset_effective: Mapped[str] = mapped_column(String)
    reference_edition: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


def latest_determination_ids():
    """Subquery of the newest determination id per claim. A rescore appends a row; every
    portfolio read (dashboard, lists, precision) must count a claim once, by its latest verdict."""
    return select(func.max(Determination.id)).group_by(Determination.claim_id)


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


class Remittance(Base):
    """Remittance advice (port of CIE's ERA): the Fund's payment record to ONE provider for ONE
    paid batch — what was billed, what was paid and why any line was reduced. Issued when the
    batch is paid; the provider's system fetches and acknowledges it over the rails channel."""
    __tablename__ = "remittance"
    __table_args__ = (UniqueConstraint("batch_id", "provider_id", name="uq_remittance_batch_provider"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ref: Mapped[str] = mapped_column(String, unique=True, index=True)        # ERA-…
    invoice_ref: Mapped[str] = mapped_column(String)                         # INV-…
    payment_ref: Mapped[str] = mapped_column(String)                         # BATCH-<id>
    batch_id: Mapped[int] = mapped_column(ForeignKey("payment_batch.id"), index=True)
    provider_id: Mapped[str] = mapped_column(String, index=True)
    period_from: Mapped[Optional[date]] = mapped_column(Date, nullable=True)  # service dates covered
    period_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    n_claims: Mapped[int] = mapped_column(Integer, default=0)
    total_billed: Mapped[float] = mapped_column(Float, default=0.0)
    total_paid: Mapped[float] = mapped_column(Float, default=0.0)
    total_reduced: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String, default="REMITTED", index=True)   # REMITTED | ACKNOWLEDGED
    issued_by: Mapped[str] = mapped_column(String, default="")
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class RemittanceLine(Base):
    """One adjudicated billing line on a remittance, reconciled to what was actually paid."""
    __tablename__ = "remittance_line"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    remittance_id: Mapped[int] = mapped_column(ForeignKey("remittance.id"), index=True)
    claim_id: Mapped[str] = mapped_column(String, index=True)
    party_token: Mapped[str] = mapped_column(String, default="")             # pseudonymous claimant
    kind: Mapped[str] = mapped_column(String)
    code: Mapped[str] = mapped_column(String)
    service_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    billed: Mapped[float] = mapped_column(Float, default=0.0)
    paid: Mapped[float] = mapped_column(Float, default=0.0)
    reduced: Mapped[float] = mapped_column(Float, default=0.0)
    reasons: Mapped[list] = mapped_column(JSON, default=list)


class MedicalReport(Base):
    """A statutory medical report a provider files with the Fund (port of CIE's medical reports):
    the RAF 1 medical report or the RAF 4 serious injury assessment. Self-describing — sections ->
    fields -> {label, value} — so it is stored and printed exactly as filed. Keyed to a claim by
    the reference the provider quoted; the patient is never a structured field."""
    __tablename__ = "medical_report"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ref: Mapped[str] = mapped_column(String, unique=True, index=True)        # MR-…
    form_code: Mapped[str] = mapped_column(String, index=True)               # RAF1-MR | RAF4
    form_title: Mapped[str] = mapped_column(String, default="")
    provider_id: Mapped[str] = mapped_column(String, index=True)
    claim_ref: Mapped[str] = mapped_column(String, index=True)               # as the provider quoted it
    claim_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)   # resolved
    complete: Mapped[bool] = mapped_column(default=False)                    # judged by the Fund
    missing: Mapped[list] = mapped_column(JSON, default=list)                # required fields left empty
    sections: Mapped[list] = mapped_column(JSON, default=list)
    idempotency_key: Mapped[str] = mapped_column(String, unique=True, index=True)
    body_hash: Mapped[str] = mapped_column(String)
    received_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


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


class Case(Base):
    """Investigation / review case (§8e): OPEN -> IN_REVIEW / ESCALATED -> CLOSED.
    Lanes: REVIEW (HANDLER), BLOCK / CLAWBACK (INVESTIGATOR); escalation -> INVESTIGATOR pool. SLA
    by priority; rand-at-stake; outcome capture (verdict, root cause, recovered/prevented) on close."""
    __tablename__ = "cases"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    claim_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("claims.claim_id"), nullable=True, index=True)
    lane: Mapped[str] = mapped_column(String, index=True)
    status: Mapped[str] = mapped_column(String, default="OPEN", index=True)
    priority: Mapped[int] = mapped_column(Integer, default=3)
    reason: Mapped[str] = mapped_column(String)
    rand_at_stake: Mapped[float] = mapped_column(Float, default=0.0)
    assigned_to: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    verdict: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    root_cause: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    rand_recovered: Mapped[float] = mapped_column(Float, default=0.0)
    rand_prevented: Mapped[float] = mapped_column(Float, default=0.0)
    opened_by: Mapped[str] = mapped_column(String)
    opened_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    due_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class CaseNote(Base):
    """Append-only case notes (§8e)."""
    __tablename__ = "case_notes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), index=True)
    author: Mapped[str] = mapped_column(String)
    body: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Dispute(Base):
    """Objection / dispute register (§6 — the CIE s91-objection pattern generalised):
    LODGED -> UNDER_RECONSIDERATION -> UPHELD / REJECTED -> REFERRED -> RESOLVED (or WITHDRAWN).
    Reconsideration is internal; referral routes to the HPCSA tribunal (serious injury) or the
    litigation hand-off (channel + linked_ref)."""
    __tablename__ = "disputes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    claim_id: Mapped[str] = mapped_column(ForeignKey("claims.claim_id"), index=True)
    subject: Mapped[str] = mapped_column(String)          # MERITS|QUANTUM|TARIFF|REPUDIATION|SERIOUS_INJURY
    raised_by: Mapped[str] = mapped_column(String)        # CLAIMANT|PROVIDER|ATTORNEY
    grounds: Mapped[str] = mapped_column(String, default="")
    status: Mapped[str] = mapped_column(String, default="LODGED", index=True)
    channel: Mapped[Optional[str]] = mapped_column(String, nullable=True)   # INTERNAL|HPCSA_TRIBUNAL|LITIGATION
    outcome: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    linked_ref: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    opened_by: Mapped[str] = mapped_column(String)
    opened_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    deadline: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class Notification(Base):
    """POPIA-minimal outbound notification outbox (§12.8) — claim reference + what's outstanding
    only, never medical or quantum detail. The recipient is the pseudonymous party token; the
    actual contact (phone/email, PII) is resolved externally at delivery. This is the per-claim log."""
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    claim_id: Mapped[str] = mapped_column(ForeignKey("claims.claim_id"), index=True)
    party_token: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    channel: Mapped[str] = mapped_column(String)          # SMS | EMAIL | NONE
    event: Mapped[str] = mapped_column(String, index=True)
    body: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="PENDING", index=True)  # PENDING|SENT|FAILED|SUPPRESSED
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class NotificationPref(Base):
    """Opt-in channel preference on the (pseudonymous) party record (§12.8) — POPIA opt-in;
    notifications are SUPPRESSED unless the party has opted in to a channel."""
    __tablename__ = "notification_pref"
    party_token: Mapped[str] = mapped_column(String, primary_key=True)
    channel: Mapped[str] = mapped_column(String, default="NONE")   # SMS | EMAIL | NONE
    opted_in: Mapped[bool] = mapped_column(default=False)


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
