"""Assemble the engine's RefBook + Ruleset from the reference tables (scheme rules as data)."""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

import engine

from . import models
from .crosswalk import apply_crosswalk


def _norm(code: str) -> str:
    """Tariff-code normalisation — must match engine.reference.resolve (strip leading zeros)."""
    return code.lstrip("0") or "0"


def _kn(kind: str, code: str) -> tuple[str, str]:
    return (kind, _norm(code) if kind == "TARIFF" else code)


def build_refbook(db: Session, nappi_codes=None) -> engine.RefBook:
    # TARIFF-family dicts are keyed by the NORMALISED code (the resolver strips leading zeros);
    # NAPPI codes and the non-benchmarkable set are keyed on the raw code.
    #
    # SEP scalability: the NAPPI table is ~540k rows in production, so loading it whole per
    # claim would be fatal. When `nappi_codes` is given (the codes on the claim being priced) we
    # fetch only those (indexed lookups); `None` loads all (fine for small/test corpora).
    negotiated = {_kn(r.kind, r.code): r.rate for r in db.scalars(select(models.RefNegotiated))}
    rpl: dict = defaultdict(dict)                     # code -> {discipline -> rate}
    for r in db.scalars(select(models.RefRpl)):
        rpl[_norm(r.code)][r.discipline] = r.rate
    rpl = dict(rpl)
    raf2022 = {_norm(r.code): r.rate for r in db.scalars(select(models.RefRaf2022))}
    empirical = {_kn(r.kind, r.code): r.median for r in db.scalars(select(models.RefEmpirical))}
    non_bench = {r.code for r in db.scalars(select(models.RefNonBench))}

    if nappi_codes is None:
        sep = {r.nappi_code: r.sep for r in db.scalars(select(models.RefNappiSep))}
    elif nappi_codes:
        sep = {r.nappi_code: r.sep for r in db.scalars(
            select(models.RefNappiSep).where(models.RefNappiSep.nappi_code.in_(set(nappi_codes))))}
    else:
        sep = {}
    book = engine.RefBook(negotiated=negotiated, rpl=rpl, raf2022=raf2022,
                          empirical=empirical, sep=sep, non_benchmarkable=non_bench)
    apply_crosswalk(book)         # activate SME-CONFIRMED COIDA→RAF equivalences (no-op until confirmed)
    return book


def build_ruleset(db: Session) -> engine.Ruleset:
    caps = [(r.effective_from, r.annual_cap) for r in db.scalars(select(models.RefCap))]
    preauth = {r.code for r in db.scalars(select(models.RefPreauth))}
    return engine.Ruleset(caps=caps, preauth_required=preauth)
