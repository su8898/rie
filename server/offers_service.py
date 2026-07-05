"""Offer builder + persistence — assemble heads of damage into an offer (domain-logic §5, §8).

`compute_offer` is the stateless what-if (from a raw payload). `persist_offer` is the
operational version: it reads the *stored* claim and the *merits machine* state, computes each
head via the engine (past medical from adjudicated lines, loss of earnings through the Sweatman
cap engine, general damages gated by the serious-injury process), and stores an Offer + its
heads. An offer is ASSEMBLED only when merits are accepted; otherwise it is HELD. The lifecycle
`make_offer` gate requires an ASSEMBLED offer.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

import engine

from . import adapter, models
from .reference_data import build_refbook, build_ruleset


def compute_offer(db: Session, payload: dict, today: Optional[date] = None) -> dict:
    claim = adapter.json_to_claim(payload)
    nappi_codes = {l.code for l in claim.lines if l.kind == "NAPPI"}
    book, rs = build_refbook(db, nappi_codes), build_ruleset(db)
    accidents = [adapter.accident_to_engine(r) for r in db.scalars(select(models.AccidentRecord))]

    record = engine.process_claim(
        claim, accidents, book, rs, today=today or date.today(),
        accident_dx_regions=set(payload.get("accident_dx_regions", [])),
    )

    hi = payload.get("heads_input", {})
    heads: dict = {"past_medical": record["medical_payable"]}                  # already apportioned

    if loe := hi.get("loss_of_earnings"):
        total, worksheet = engine.head_loss_of_earnings(
            [float(x) for x in loe["annual_losses"]], claim, rs)
        heads["loss_of_earnings"] = {"total": total, "worksheet": worksheet}

    if los := hi.get("loss_of_support"):                                      # §5c — dependants (deceased)
        total, worksheet = engine.head_loss_of_support(
            [float(x) for x in los["annual_losses"]], claim, rs)
        heads["loss_of_support"] = {"total": total, "worksheet": worksheet}

    if gd := hi.get("general_damages"):
        amount, gd_reasons = engine.head_general_damages(
            claim, float(gd.get("band_p25", 0.0)), float(gd.get("band_p75", 0.0)),
            float(gd["proposed"]))
        heads["general_damages"] = {"amount": amount, "reasons": gd_reasons}

    if fun := hi.get("funeral"):                                              # §5e — deceased claimant
        amount, fun_reasons = engine.head_funeral(
            claim, float(fun["necessary_costs"]), float(fun.get("non_necessary", 0.0)))
        heads["funeral"] = {"amount": amount, "reasons": fun_reasons}

    gated_by: list[str] = []
    if claim.merits_accepted is not True:                                     # §4c — no offer without merits
        gated_by.append("held_for_merits")
        offer_total = 0.0
    else:
        offer_total = (heads["past_medical"]
                       + heads.get("loss_of_earnings", {}).get("total", 0.0)
                       + heads.get("loss_of_support", {}).get("total", 0.0)
                       + heads.get("general_damages", {}).get("amount", 0.0)
                       + heads.get("funeral", {}).get("amount", 0.0))

    return {"claim_id": claim.claim_id, "determination": record, "heads": heads,
            "offer_total": round(offer_total, 2), "gated_by": gated_by}


def persist_offer(db: Session, claim_id: str, heads_input: dict, user: dict,
                  today: Optional[date] = None) -> dict:
    claim_rec = db.get(models.ClaimRecord, claim_id)
    if claim_rec is None:
        raise ValueError(f"claim {claim_id} not found")

    payload = dict(claim_rec.raw)                       # replay the stored claim
    merits = db.get(models.MeritsDetermination, claim_id)
    if merits is not None and merits.status == "ACCEPTED":
        payload["merits_accepted"] = True
        payload["fault_pct"] = merits.fault_pct if merits.fault_pct is not None else 0.0
    elif merits is not None and merits.status == "REJECTED":
        payload["merits_accepted"] = False
    # serious-injury process gates general damages (§5d): only an accepted/upheld RAF 4 opens GD
    si = db.scalar(select(models.SeriousInjury).where(models.SeriousInjury.claim_id == claim_id)
                   .order_by(desc(models.SeriousInjury.id)))
    if si is not None:
        payload["si_accepted"] = si.status in ("RAF_ACCEPTED", "UPHELD")
    payload["heads_input"] = heads_input or {}

    result = compute_offer(db, payload, today=today)
    status = "HELD" if result["gated_by"] else "ASSEMBLED"
    offer = models.Offer(claim_id=claim_id, status=status, total=result["offer_total"],
                         gated_by=result["gated_by"])
    db.add(offer)
    db.flush()

    heads = result["heads"]
    db.add(models.OfferHead(offer_id=offer.id, head="PAST_MEDICAL",
                            amount=heads.get("past_medical", 0.0), detail={}))
    if "loss_of_earnings" in heads:
        db.add(models.OfferHead(offer_id=offer.id, head="LOSS_OF_EARNINGS",
                                amount=heads["loss_of_earnings"]["total"],
                                detail={"worksheet": heads["loss_of_earnings"]["worksheet"]}))
    if "loss_of_support" in heads:
        db.add(models.OfferHead(offer_id=offer.id, head="LOSS_OF_SUPPORT",
                                amount=heads["loss_of_support"]["total"],
                                detail={"worksheet": heads["loss_of_support"]["worksheet"]}))
    if "general_damages" in heads:
        db.add(models.OfferHead(offer_id=offer.id, head="GENERAL_DAMAGES",
                                amount=heads["general_damages"]["amount"],
                                detail={"reasons": heads["general_damages"]["reasons"]}))
    if "funeral" in heads:
        db.add(models.OfferHead(offer_id=offer.id, head="FUNERAL",
                                amount=heads["funeral"]["amount"],
                                detail={"reasons": heads["funeral"]["reasons"]}))
    db.commit()
    return {"offer_id": offer.id, "status": status, **result}


def latest_offer(db: Session, claim_id: str) -> Optional[dict]:
    o = db.scalar(select(models.Offer).where(models.Offer.claim_id == claim_id)
                  .order_by(desc(models.Offer.id)))
    if o is None:
        return None
    heads = db.scalars(select(models.OfferHead).where(models.OfferHead.offer_id == o.id))
    return {"offer_id": o.id, "claim_id": o.claim_id, "status": o.status, "total": o.total,
            "gated_by": o.gated_by,
            "heads": [{"head": h.head, "amount": h.amount, "detail": h.detail} for h in heads]}
