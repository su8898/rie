"""Payment eligibility — the last gate (domain-logic §8e).

A claim pays only if its disposition is CLEAN/ADJUSTED, it is validated, merits are accepted
(for PERSONAL claims), the payee is verified, the attorney is in standing, and the claimant is
alive. Net payable nets off any interim payment (s17(6)).
"""
from __future__ import annotations

from decimal import Decimal

from .models import Claim
from .vocab import Category, D, money


def eligible_to_pay(c: Claim, disp: Category, validated: bool,
                    interim_paid: float, payable: float) -> tuple[bool, float, list[str]]:
    holds = []
    if disp not in (Category.CLEAN, Category.ADJUSTED): holds.append(f"held_{disp.name.lower()}")
    if not validated:                                   holds.append("held_for_validation")
    if c.merits_accepted is not True and c.claim_type == "PERSONAL":
        holds.append("held_for_merits")
    if not c.payee_verified:                            holds.append("PAYEE_UNVERIFIED")
    if not c.attorney_in_standing:                      holds.append("ATTORNEY_NOT_IN_STANDING")
    if c.claimant_deceased_on:                          holds.append("LIFE_STATUS_MISMATCH")
    return (not holds), money(max(D(payable) - D(interim_paid), Decimal(0))), holds
