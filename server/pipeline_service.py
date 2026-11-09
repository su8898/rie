"""assess_and_store — run one claim through the engine and persist the determination.

Loads the accident graph, runs `engine.process_claim`, then persists: the (immutable) claim +
its billing lines, the accident (created on first touch or updated with the joined claim), and
the determination. The accident graph accumulates across submissions — the corroboration
sensor network — and the billing lines feed leakage accounting.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

import engine

from . import adapter, models
from .pseudonymise import RAW_SA_ID, pseudonymise_ingest
from .reference_data import build_mode_overrides, build_refbook, build_ruleset


class DuplicateClaim(ValueError):
    """The claim_id is already in the immutable corpus; a re-determination must be explicit (rescore)."""


def _optdate(s) -> Optional[date]:
    return date.fromisoformat(s) if s else None


def _line_details(claim: engine.Claim, book: engine.RefBook, rs: engine.Ruleset,
                  tier: str, dx_regions: set[str], prior: frozenset) -> list[dict]:
    """Per-line adjudication detail (mirrors process_claim's internal line loop) for storage."""
    seen: set = set()
    usage: dict = {}
    out = []
    for line in claim.lines:
        lr = engine.adjudicate_line(claim, line, book, rs, tier, seen, set(dx_regions), prior, usage)
        rate, _src, status = engine.resolve(book, line.kind, line.code, tier)
        out.append({
            "provider_id": line.provider_id,
            "kind": line.kind, "code": line.code, "billed": line.amount, "payable": lr.payable,
            "reference": engine.money(engine.D(rate) * engine.D(line.qty)) if rate is not None else None,
            "src": lr.src, "legal_status": status.name if status else None,
            "needs_review": lr.needs_review, "reasons": lr.reasons,
            "service_date": line.service_date,
        })
    return out


def prior_lines(db: Session, claim: engine.Claim) -> frozenset:
    """§4e / s17(5) — the pay-once ledger: every line already PAID (payable > 0) on ANOTHER claim
    for this party, as engine line keys. Threaded into the engine so a service billed again on a
    second claim (any claim type) is SUPPLIER_PRECLUSION, not paid twice."""
    rows = db.execute(
        select(models.BillingLineRecord)
        .join(models.ClaimRecord, models.ClaimRecord.claim_id == models.BillingLineRecord.claim_id)
        .where(models.ClaimRecord.party_token == claim.party_token,
               models.BillingLineRecord.claim_id != claim.claim_id,
               models.BillingLineRecord.payable > 0,
               models.BillingLineRecord.service_date.is_not(None))
    ).scalars()
    return frozenset(
        (claim.party_token, r.provider_id, r.service_date, r.kind,
         engine.normalise_code(r.kind, r.code), r.billed)
        for r in rows)


def load_graph(db: Session, claim: engine.Claim) -> tuple[list[engine.Accident], dict]:
    """The accident graph as engine objects (pilot scale: whole graph), each accident carrying the
    claimants (party tokens of PERSONAL claims) already anchored to it — excluding this claim, so
    a rescore never flags itself as its own duplicate."""
    recs = list(db.scalars(select(models.AccidentRecord)))
    personal = dict(db.execute(
        select(models.ClaimRecord.claim_id, models.ClaimRecord.party_token)
        .where(models.ClaimRecord.claim_type == "PERSONAL")).all())
    accidents = [adapter.accident_to_engine(
        r, {personal[cid] for cid in (r.claims or []) if cid in personal and cid != claim.claim_id})
        for r in recs]
    return accidents, {r.accident_id: r for r in recs}


def assess_and_store(db: Session, payload: dict, today: Optional[date] = None,
                     *, rescore: bool = False) -> dict:
    """Score one claim and persist. A claim_id already in the corpus is refused (DuplicateClaim)
    unless `rescore=True` — the explicit ADMIN re-determination path, which appends a new
    determination over the *stored* payload so the record and its lines never diverge."""
    payload = pseudonymise_ingest(payload)              # POPIA — derive P_* from a raw ID, strip PII (§2)
    claim = adapter.json_to_claim(payload)
    if RAW_SA_ID.match(claim.party_token.strip()):             # POPIA — a raw identity number is never stored
        raise ValueError("party_token looks like a raw national ID — send it as national_id")
    existing = db.get(models.ClaimRecord, claim.claim_id)
    if existing is not None and not rescore:
        raise DuplicateClaim(f"claim {claim.claim_id} already submitted — use the ADMIN rescore to re-determine")
    nappi_codes = {l.code for l in claim.lines if l.kind == "NAPPI"}
    book, rs = build_refbook(db, nappi_codes), build_ruleset(db)
    tier = payload.get("provider_tier", "GP")
    dx_regions = set(payload.get("accident_dx_regions", []))

    accidents, rec_by_id = load_graph(db, claim)
    prior = prior_lines(db, claim)                              # §4e — pay once across claims

    record = engine.process_claim(
        claim, accidents, book, rs, today=today or date.today(), provider_tier=tier,
        accident_dx_regions=dx_regions, cohort_is_bus_taxi=bool(payload.get("cohort_is_bus_taxi", False)),
        conv_floor_p10=float(payload.get("conv_floor_p10", 20.0)),
        summons_served=_optdate(payload.get("summons_served")),
        mode_overrides=build_mode_overrides(db),                # §11 — ADMIN signal-mode overrides
        seen_lines=set(prior),
    )
    lines = _line_details(claim, book, rs, tier, dx_regions, prior)
    _persist(db, claim, payload, record, rec_by_id, lines)
    return record


def _persist(db: Session, claim: engine.Claim, payload: dict, record: dict,
             rec_by_id: dict, lines: list[dict]) -> None:
    aid = record["accident_id"]
    existing_acc = rec_by_id.get(aid)
    if existing_acc is not None:                                # JOINED / AUTO_JOINED
        claims = list(existing_acc.claims or [])
        if claim.claim_id not in claims:
            claims.append(claim.claim_id)
        existing_acc.claims = claims                            # reassign so JSON change is tracked
    else:                                                       # CREATED / WORKLIST — own accident on first touch
        db.add(models.AccidentRecord(
            accident_id=aid, case_number=engine.normalise_cas(claim.case_number_raw),
            when_=claim.accident_date, where_="", vehicles=[], parties=[claim.party_token],
            oar_occupants=None, sources={}, claims=[claim.claim_id],
        ))

    if db.get(models.ClaimRecord, claim.claim_id) is None:     # immutable corpus — write once (rescore never rewrites)
        db.add(models.ClaimRecord(
            claim_id=claim.claim_id, claim_type=claim.claim_type, party_token=claim.party_token,
            accident_date=claim.accident_date, lodged_on=claim.lodged_on, raw=payload,
        ))
        db.flush()                                              # insert the claim before its FK children (Postgres enforces order)
        for ld in lines:                                        # billing lines feed leakage
            db.add(models.BillingLineRecord(claim_id=claim.claim_id, **ld))
        db.add(models.ClaimLifecycle(claim_id=claim.claim_id, stage="LODGED"))
        if claim.claim_type == "PERSONAL":                      # merits determination opens PENDING
            db.add(models.MeritsDetermination(claim_id=claim.claim_id, status="PENDING"))

    db.add(models.Determination(
        claim_id=record["claim_id"], accident_id=aid, accident_action=record["accident_action"],
        band=record["band"], score=record["score"], disposition=record["disposition"],
        validated=record["validated"], convergence=record["convergence"],
        medical_payable=record["medical_payable"], net_payable=record["net_payable"],
        eligible_to_pay=record["eligible_to_pay"], reasons=record["reasons"],
        shadow_signals=record["shadow_signals"], holds=record["holds"],
        needs_review=record["needs_review"], advisory_signals=record["advisory_signals"],
        accident_candidate=record["accident_candidate"],
        engine_version=record["engine_version"], ruleset_effective=record["ruleset_effective"],
        reference_edition=record["reference_edition"],
    ))
    db.commit()
