"""Assemble the engine's RefBook + Ruleset from the reference tables (scheme rules as data)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

import engine

from . import models


def _norm(code: str) -> str:
    """Tariff-code normalisation — must match engine.reference.resolve (strip leading zeros)."""
    return code.lstrip("0") or "0"


def _kn(kind: str, code: str) -> tuple[str, str]:
    return (kind, _norm(code) if kind == "TARIFF" else code)


def build_refbook(db: Session) -> engine.RefBook:
    # TARIFF-family dicts are keyed by the NORMALISED code (the resolver strips leading zeros);
    # NAPPI codes and the non-benchmarkable set are keyed on the raw code.
    negotiated = {_kn(r.kind, r.code): r.rate for r in db.scalars(select(models.RefNegotiated))}
    rpl = {_norm(r.code): (r.gp, r.spec) for r in db.scalars(select(models.RefRpl))}
    raf2022 = {_norm(r.code): r.rate for r in db.scalars(select(models.RefRaf2022))}
    empirical = {_kn(r.kind, r.code): r.median for r in db.scalars(select(models.RefEmpirical))}
    sep = {r.nappi_code: r.sep for r in db.scalars(select(models.RefNappiSep))}
    non_bench = {r.code for r in db.scalars(select(models.RefNonBench))}
    return engine.RefBook(negotiated=negotiated, rpl=rpl, raf2022=raf2022,
                          empirical=empirical, sep=sep, non_benchmarkable=non_bench)


def build_ruleset(db: Session) -> engine.Ruleset:
    caps = [(r.effective_from, r.annual_cap) for r in db.scalars(select(models.RefCap))]
    preauth = {r.code for r in db.scalars(select(models.RefPreauth))}
    return engine.Ruleset(caps=caps, preauth_required=preauth)
