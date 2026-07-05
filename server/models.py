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
