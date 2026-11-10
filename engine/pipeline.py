"""The pipeline — one claim, end to end (domain-logic §11).

process_claim is the brain, invoked once per claim. Deterministic and side-effect-free apart
from anchoring the claim to the accident graph. Returns the provenance-stamped determination
record.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from .accidents import resolve_accident
from .adjudication import adjudicate_line
from .corroboration import convergence, corroboration_signals
from .disposition import disposition
from .gates import merits_gate, prescription_gates, s24_gates, standing_gates
from .heads import head_past_medical
from .models import Accident, Activity, Claim, Ruleset
from .payments import eligible_to_pay
from .reference import RefBook
from .scoring import score_and_band
from .signals import billing_signals


def process_claim(c: Claim, accidents: list[Accident], book: RefBook, rs: Ruleset,
                  today: date, provider_tier: str = "GP",
                  accident_dx_regions: set[str] = frozenset(),
                  seen_lines: Optional[set] = None, cohort_is_bus_taxi: bool = False,
                  conv_floor_p10: float = 20.0, summons_served: Optional[date] = None,
                  mode_overrides: Optional[dict] = None,
                  activity: Optional[Activity] = None) -> dict:
    """The brain, invoked once per claim. Deterministic. Returns the determination record.
    `seen_lines` is the pay-once ledger across claims (§4e, s17(5)): the caller threads the
    party's lines already paid elsewhere; this claim's lines are added to it on return."""
    seen_lines = seen_lines if seen_lines is not None else set()
    prior_lines = frozenset(seen_lines)

    # A. anchor to the accident graph and refresh corroboration          (§6.0)
    accident, action = resolve_accident(c, accidents)
    accident.claims.append(c.claim_id)
    graph_reasons = corroboration_signals(accident, cohort_is_bus_taxi, conv_floor_p10)
    dup_claim = (["DUPLICATE_CLAIM"] if c.claim_type == "PERSONAL"
                 and c.party_token in accident.claimants else [])   # one claim per claimant per accident
    if c.claim_type == "PERSONAL":
        accident.claimants.add(c.party_token)

    # B. grounded gates                                                   (§4)
    deceased_pre = bool(c.claimant_deceased_on and
                        any(l.service_date > c.claimant_deceased_on for l in c.lines))
    gate_reasons = (prescription_gates(c, rs, today, summons_served)
                    + s24_gates(c) + standing_gates(c, deceased_pre) + merits_gate(c) + dup_claim)
    validated = not any(r in ("S24_INCOMPLETE", "OAR_MISSING") for r in gate_reasons)

    # C. per-line adjudication                                        (§3, §5f)
    seen, auth_usage = set(), {}
    line_results = [adjudicate_line(c, l, book, rs, provider_tier, seen, set(accident_dx_regions),
                                    prior_lines, auth_usage) for l in c.lines]
    seen_lines |= seen
    line_reasons = [r for lr in line_results for r in lr.reasons]
    billing_reasons = billing_signals(c, rs, provider_tier, activity)       # §10

    # D. heads (medical here; earnings/GD computed when their inputs arrive) (§5)
    medical_payable = head_past_medical(line_results, c.fault_pct)

    # E. score, band, disposition                                    (§10, §9)
    assessment = score_and_band(gate_reasons + line_reasons + billing_reasons + graph_reasons,
                                mode_overrides)
    disp = disposition(assessment, merits_pending=(c.merits_accepted is None
                                                   and c.claim_type == "PERSONAL"))

    # F. payment eligibility                                             (§8e)
    ok, net_payable, holds = eligible_to_pay(c, disp, validated,
                                             interim_paid=0.0, payable=medical_payable)

    return {  # the determination record — provenance-stamped, reproducible
        "claim_id": c.claim_id, "accident_id": accident.accident_id,
        "accident_action": action, "convergence": convergence(accident),
        "validated": validated, "band": assessment.band.name, "score": assessment.score,
        "reasons": assessment.reasons, "shadow_signals": assessment.shadow,
        "disposition": disp.name, "medical_payable": medical_payable,
        "eligible_to_pay": ok, "net_payable": net_payable, "holds": holds,
        "needs_review": any(lr.needs_review for lr in line_results),
        "advisory_signals": assessment.advisory, "accident_candidate": accident.worklist_candidate,
        "engine_version": assessment.engine_version,
        "ruleset_effective": c.accident_date.isoformat(), "reference_edition": "RPL-2026",
    }
