"""Offer builder — assemble heads of damage into an offer (domain-logic §5, §8).

Read-only "what-if": given a claim payload (+ heads_input), compute each head via the engine —
past medical from adjudicated lines, loss of earnings through the Sweatman cap engine, general
damages gated by the serious-injury process — and gate the offer on merits acceptance.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import select

import engine

from . import adapter, models
from .reference_data import build_refbook, build_ruleset


def compute_offer(db, payload: dict, today: Optional[date] = None) -> dict:
    claim = adapter.json_to_claim(payload)
    book, rs = build_refbook(db), build_ruleset(db)
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

    if gd := hi.get("general_damages"):
        amount, gd_reasons = engine.head_general_damages(
            claim, float(gd.get("band_p25", 0.0)), float(gd.get("band_p75", 0.0)),
            float(gd["proposed"]))
        heads["general_damages"] = {"amount": amount, "reasons": gd_reasons}

    # No head pays and no offer issues without an accepted merits determination (§4c).
    gated_by: list[str] = []
    if claim.merits_accepted is not True:
        gated_by.append("held_for_merits")
        offer_total = 0.0
    else:
        offer_total = (heads["past_medical"]
                       + heads.get("loss_of_earnings", {}).get("total", 0.0)
                       + heads.get("general_damages", {}).get("amount", 0.0))

    return {"claim_id": claim.claim_id, "determination": record, "heads": heads,
            "offer_total": round(offer_total, 2), "gated_by": gated_by}
