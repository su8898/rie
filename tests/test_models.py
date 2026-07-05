"""Per-function unit tests for engine.models — concrete value assertions.

Ruleset.cap_at(accident_date) = latest cap whose effective_from <= accident_date, else 0.0.
Also spot-checks dataclass defaults so the shapes stay pinned.
"""
from __future__ import annotations

from datetime import date

from engine.models import (
    Accident, Authorisation, Claim, Line, LineResult, Ruleset, Undertaking,
)
from engine.vocab import Band


# ── Ruleset.cap_at ───────────────────────────────────────────────────────────
def test_cap_at_empty_caps_is_zero():
    assert Ruleset(caps=[]).cap_at(date(2020, 1, 1)) == 0.0


def test_cap_at_none_effective_before_date_is_zero():
    rs = Ruleset(caps=[(date(2026, 1, 1), 100.0)])
    assert rs.cap_at(date(2020, 1, 1)) == 0.0


def test_cap_at_picks_latest_effective_on_or_before():
    rs = Ruleset(caps=[(date(2015, 1, 1), 160000.0), (date(2026, 1, 31), 378581.0)])
    assert rs.cap_at(date(2020, 6, 1)) == 160000.0
    assert rs.cap_at(date(2026, 2, 1)) == 378581.0


def test_cap_at_boundary_is_inclusive():
    rs = Ruleset(caps=[(date(2015, 1, 1), 160000.0), (date(2026, 1, 31), 378581.0)])
    # accident exactly on the 2026 effective date -> uses 378581 (eff <= date)
    assert rs.cap_at(date(2026, 1, 31)) == 378581.0


def test_cap_at_sorts_unsorted_caps():
    rs = Ruleset(caps=[(date(2026, 1, 31), 378581.0), (date(2015, 1, 1), 160000.0)])
    assert rs.cap_at(date(2020, 1, 1)) == 160000.0


def test_cap_at_single_cap_effective():
    rs = Ruleset(caps=[(date(2015, 1, 1), 160000.0)])
    assert rs.cap_at(date(2025, 1, 1)) == 160000.0


# ── dataclass defaults ───────────────────────────────────────────────────────
def test_ruleset_defaults():
    rs = Ruleset()
    assert rs.lodgement_years_identified == 3
    assert rs.lodgement_years_hitrun == 2
    assert rs.summons_years == 5
    assert rs.investigation_days == 120
    assert rs.wpi_threshold == 30.0
    assert rs.caps == [] and rs.preauth_required == set() and rs.s19_grounds == set()


def test_line_defaults():
    line = Line(kind="TARIFF", code="0190", qty=1.0, amount=500.0,
                service_date=date(2026, 3, 1), provider_id="PR1", dx="S72")
    assert line.emergency is False and line.scheme_paid is False


def test_authorisation_default_status_approved():
    auth = Authorisation(codes={"0190"}, qty_limit=10.0, ceiling=1000.0,
                         valid_from=date(2026, 1, 1), valid_to=date(2026, 12, 31))
    assert auth.status == "APPROVED"


def test_undertaking_defaults():
    u = Undertaking(active=True, scope_dx={"S72"}, scope_coded=True)
    assert u.authorisations == []


def test_claim_defaults():
    c = Claim(claim_id="R", claim_type="SUPPLIER", party_token="P",
              accident_date=date(2026, 2, 1), lodged_on=date(2026, 3, 1),
              case_number_raw=None, documents={}, lines=[])
    assert c.heads == {}
    assert c.hit_and_run is False and c.prescription_suspended is False
    assert c.fault_pct is None and c.merits_accepted is None and c.merits_ground is None
    assert c.si_accepted is None and c.undertaking is None and c.claimant_deceased_on is None
    assert c.payee_verified is False
    assert c.attorney_in_standing is True and c.provider_registered is True


def test_accident_defaults():
    a = Accident(accident_id="A", case_number=None, when=date(2026, 2, 1), where="",
                 vehicles=set(), parties=set(), oar_occupants=None)
    assert a.sources == {} and a.claims == []


def test_line_result_default_needs_review_false():
    lr = LineResult(payable=100.0, reasons=[], src="x")
    assert lr.needs_review is False


def test_assessment_default_engine_version():
    from engine.models import Assessment
    a = Assessment(reasons=[], shadow=[], score=0, band=Band.GREEN)
    assert a.engine_version == "rie-scorer v1"
