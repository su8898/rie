"""Shared claim scenarios, parameterised by engine module.

Each builder takes a module `M` (either `spec.rie_engine`, the single-file oracle, or the
`engine` package) and returns the kwargs for `M.process_claim`, constructed from *that module's*
own dataclasses. Because both modules expose identical class names, one builder feeds both — so
the conformance test can assert byte-for-byte equality of the determination records, and the
unit tests can drive the real engine directly.

The set exercises every branch of every engine function: reference tiers (negotiated / RPL /
RPL-specialist / interdicted / endogenous / NAPPI+fee / OCR-guard / non-benchmarkable /
uncovered), all gates, undertaking + pre-auth reconciliation, duplicates, DX mismatch,
accident resolution (JOINED / WORKLIST / CREATED), corroboration (surge / thin), heads
apportionment, disposition precedence, and every payment hold.
"""
from __future__ import annotations

from datetime import date

TODAY = date(2026, 7, 5)

DEFAULT_DOCS = {
    "PERSONAL":            {"RAF1": True, "OAR": True, "ID": True, "BANK": True},
    "SUPPLIER":            {"RAF2": True, "OAR": True, "INVOICES": True, "BANK": True},
    "UNDERTAKING_INVOICE": {"INVOICES": True, "BANK": True},
}


# ── builders (module-parameterised) ──────────────────────────────────────────
def _book(M):
    # TARIFF-family dicts are keyed on the NORMALISED code (resolve strips leading zeros:
    # "0190"->"190"); NAPPI codes key on the raw code. The non-benchmarkable set, the
    # pre-auth set and authorisation codes normalise themselves on construction (H3).
    return M.RefBook(
        negotiated={("TARIFF", "55"): 400.0},
        rpl={"190": {"GP": 500.0, "SPECIALIST": 700.0}, "23": {"GP": 100.0}, "100": {"GP": 200.0}},
        raf2022={"200": 300.0, "300": 50.0},
        empirical={("TARIFF", "999"): 250.0, ("TARIFF", "300"): 300.0, ("NAPPI", "888"): 90.0},
        sep={"700101": 88.40},
        non_benchmarkable={"0011"},
    )


def _rs(M):
    return M.Ruleset(
        caps=[(date(2015, 1, 1), 160000.0), (date(2026, 1, 31), 378581.0)],
        preauth_required={"0500"},
    )


def _line(M, code="0190", amount=500.0, qty=1.0, kind="TARIFF", dx="S72",
          provider="PR1", svc=date(2026, 3, 1), emergency=False, discipline=""):
    return M.Line(kind=kind, code=code, qty=qty, amount=amount, service_date=svc,
                  provider_id=provider, dx=dx, emergency=emergency, discipline=discipline)


def _claim(M, ctype="SUPPLIER", lines=None, docs=None, **kw):
    base = dict(
        claim_id="R_1", claim_type=ctype, party_token="P_1",
        accident_date=date(2026, 2, 1), lodged_on=date(2026, 3, 1),
        case_number_raw="CAS 100/02/2026",
        documents=dict(docs if docs is not None else DEFAULT_DOCS[ctype]),
        lines=lines if lines is not None else [_line(M)],
        payee_verified=True, attorney_in_standing=True, provider_registered=True,
    )
    base.update(kw)
    return M.Claim(**base)


def _accident(M, case="CAS100/02/2026", when=date(2026, 2, 1), parties=None, oar=None,
              sources=None, where="", vehicles=None, claimants=None):
    return M.Accident(accident_id="A_pre", case_number=case, when=when, where=where,
                      vehicles=set(vehicles or []), parties=set(parties or ["P_1"]),
                      oar_occupants=oar, sources=dict(sources or {}),
                      claimants=set(claimants or []))


def _undertaking(M, active=True, scope=("S72",), coded=True, auths=None):
    return M.Undertaking(active=active, scope_dx=set(scope), scope_coded=coded,
                         authorisations=list(auths or []))


def _auth(M, codes=("0190",), qty=10.0, ceiling=1000.0,
          vf=date(2026, 1, 1), vt=date(2026, 12, 31)):
    return M.Authorisation(codes=set(codes), qty_limit=qty, ceiling=ceiling,
                           valid_from=vf, valid_to=vt, status="APPROVED")


def _std(M, c, accidents=None, **kw):
    return dict(c=c, accidents=accidents if accidents is not None else [],
                book=_book(M), rs=_rs(M), today=TODAY, **kw)


# ── scenarios ────────────────────────────────────────────────────────────────
SCENARIOS: dict = {}


def scenario(fn):
    SCENARIOS[fn.__name__] = fn
    return fn


# reference tiers ------------------------------------------------------------
@scenario
def supplier_clean(M):
    return _std(M, _claim(M))


@scenario
def supplier_over_rpl(M):
    return _std(M, _claim(M, lines=[_line(M, code="0190", amount=800.0)]))


@scenario
def negotiated_enforceable_reprice(M):
    return _std(M, _claim(M, lines=[_line(M, code="0055", amount=500.0)]))


@scenario
def specialist_reprice(M):
    return _std(M, _claim(M, lines=[_line(M, code="0190", amount=800.0)]),
                provider_tier="SPECIALIST")


@scenario
def line_discipline_specialist(M):
    # per-line discipline -> SPECIALIST tariff (700); billed 800 -> repriced to 700
    return _std(M, _claim(M, lines=[_line(M, code="0190", amount=800.0, discipline="SPECIALIST")]))


@scenario
def line_discipline_unknown_falls_back_to_gp(M):
    # a discipline absent from the code's schedule -> GP fallback (500); billed 800 -> 500
    return _std(M, _claim(M, lines=[_line(M, code="0190", amount=800.0, discipline="CHIRO")]))


@scenario
def interdicted_signal_only(M):
    return _std(M, _claim(M, lines=[_line(M, code="0200", amount=400.0)]))


@scenario
def ocr_guard_endogenous(M):
    return _std(M, _claim(M, lines=[_line(M, code="0300", amount=400.0)]))


@scenario
def non_benchmarkable_line(M):
    return _std(M, _claim(M, lines=[_line(M, code="0011", amount=500.0)]))


@scenario
def uncovered_line(M):
    return _std(M, _claim(M, lines=[_line(M, code="7777", amount=500.0)]))


@scenario
def nappi_within(M):
    return _std(M, _claim(M, lines=[_line(M, kind="NAPPI", code="700101", amount=100.0)]))


@scenario
def nappi_reprice(M):
    return _std(M, _claim(M, lines=[_line(M, kind="NAPPI", code="700101", amount=150.0)]))


@scenario
def nappi_empirical(M):
    return _std(M, _claim(M, lines=[_line(M, kind="NAPPI", code="888", amount=100.0)]))


# gates ----------------------------------------------------------------------
@scenario
def personal_merits_pending(M):
    return _std(M, _claim(M, ctype="PERSONAL", merits_accepted=None))


@scenario
def personal_merits_accepted(M):
    return _std(M, _claim(M, ctype="PERSONAL", merits_accepted=True, fault_pct=0.0))


@scenario
def personal_apportioned(M):
    return _std(M, _claim(M, ctype="PERSONAL", merits_accepted=True, fault_pct=25.0))


@scenario
def merits_rejected_s19(M):
    return _std(M, _claim(M, ctype="PERSONAL", merits_accepted=False, merits_ground="S19_EXCLUSION"))


@scenario
def merits_rejected_sole(M):
    return _std(M, _claim(M, ctype="PERSONAL", merits_accepted=False, merits_ground="SOLE_NEGLIGENCE"))


@scenario
def merits_rejected_nexus(M):
    return _std(M, _claim(M, ctype="PERSONAL", merits_accepted=False, merits_ground="NO_MVA_NEXUS"))


@scenario
def prescribed_lodgement(M):
    return _std(M, _claim(M, ctype="PERSONAL", merits_accepted=True,
                          accident_date=date(2020, 1, 1), lodged_on=date(2024, 1, 1)))


@scenario
def hitrun_prescribed(M):
    return _std(M, _claim(M, ctype="PERSONAL", merits_accepted=True, hit_and_run=True,
                          accident_date=date(2023, 1, 1), lodged_on=date(2025, 8, 1)))


@scenario
def prescription_suspended_ok(M):
    return _std(M, _claim(M, ctype="PERSONAL", merits_accepted=True, prescription_suspended=True,
                          accident_date=date(2020, 1, 1), lodged_on=date(2024, 1, 1)))


@scenario
def prescribed_summons(M):
    return _std(M, _claim(M, ctype="PERSONAL", merits_accepted=True),
                summons_served=date(2031, 4, 1))


@scenario
def s24_incomplete(M):
    return _std(M, _claim(M, ctype="PERSONAL", merits_accepted=True,
                          docs={"RAF1": False, "OAR": True, "ID": True, "BANK": True}))


@scenario
def oar_missing(M):
    return _std(M, _claim(M, ctype="PERSONAL", merits_accepted=True,
                          docs={"RAF1": True, "OAR": False, "ID": True, "BANK": True}))


@scenario
def s24_and_oar(M):
    return _std(M, _claim(M, ctype="PERSONAL", merits_accepted=True,
                          docs={"RAF1": False, "OAR": False, "ID": True, "BANK": True}))


@scenario
def provider_unregistered(M):
    return _std(M, _claim(M, provider_registered=False))


@scenario
def attorney_not_in_standing(M):
    return _std(M, _claim(M, ctype="PERSONAL", merits_accepted=True, attorney_in_standing=False))


@scenario
def life_status_mismatch(M):
    return _std(M, _claim(M, ctype="PERSONAL", merits_accepted=True,
                          claimant_deceased_on=date(2026, 2, 15),
                          lines=[_line(M, svc=date(2026, 3, 1))]))


@scenario
def payee_unverified(M):
    return _std(M, _claim(M, ctype="PERSONAL", merits_accepted=True, payee_verified=False))


# line-level -----------------------------------------------------------------
@scenario
def duplicate_line(M):
    return _std(M, _claim(M, lines=[_line(M, code="0190", amount=500.0),
                                    _line(M, code="0190", amount=500.0)]))


@scenario
def service_before_accident(M):
    return _std(M, _claim(M, accident_date=date(2026, 2, 1),
                          lines=[_line(M, svc=date(2026, 1, 1))]))


@scenario
def dx_accident_mismatch(M):
    return _std(M, _claim(M, lines=[_line(M, dx="K35")]), accident_dx_regions={"S72"})


# undertaking + pre-auth -----------------------------------------------------
@scenario
def undertaking_within_auth(M):
    u = _undertaking(M, scope=("S72",), coded=True, auths=[_auth(M, codes=("0190",), ceiling=1000.0)])
    return _std(M, _claim(M, ctype="UNDERTAKING_INVOICE",
                          lines=[_line(M, code="0190", amount=500.0, dx="S72")], undertaking=u))


@scenario
def undertaking_preauth_exceeded(M):
    u = _undertaking(M, scope=("S72",), coded=True, auths=[_auth(M, codes=("0190",), ceiling=300.0)])
    return _std(M, _claim(M, ctype="UNDERTAKING_INVOICE",
                          lines=[_line(M, code="0190", amount=500.0, dx="S72")], undertaking=u))


@scenario
def undertaking_preauth_missing(M):
    u = _undertaking(M, scope=("S72",), coded=True, auths=[])
    return _std(M, _claim(M, ctype="UNDERTAKING_INVOICE",
                          lines=[_line(M, code="0500", amount=500.0, dx="S72")], undertaking=u))


@scenario
def undertaking_not_active(M):
    u = _undertaking(M, active=False)
    return _std(M, _claim(M, ctype="UNDERTAKING_INVOICE",
                          lines=[_line(M, code="0190", amount=500.0, dx="S72")], undertaking=u))


@scenario
def undertaking_scope_reject_coded(M):
    u = _undertaking(M, scope=("S72",), coded=True)
    return _std(M, _claim(M, ctype="UNDERTAKING_INVOICE",
                          lines=[_line(M, code="0190", amount=500.0, dx="K35")], undertaking=u))


@scenario
def undertaking_scope_soft_uncoded(M):
    u = _undertaking(M, scope=("S72",), coded=False)
    return _std(M, _claim(M, ctype="UNDERTAKING_INVOICE",
                          lines=[_line(M, code="0190", amount=500.0, dx="K35")], undertaking=u))


@scenario
def undertaking_emergency_bypasses_preauth(M):
    u = _undertaking(M, scope=("S72",), coded=True, auths=[])
    return _std(M, _claim(M, ctype="UNDERTAKING_INVOICE",
                          lines=[_line(M, code="0500", amount=500.0, dx="S72", emergency=True)],
                          undertaking=u))


# accident resolution + corroboration ----------------------------------------
@scenario
def accident_joined_by_cas(M):
    acc = _accident(M, parties=["P_1"], oar=5,
                    sources={"EMS": "c1", "HOSPITAL": "c2", "SAPS": "c3"})
    return _std(M, _claim(M), accidents=[acc])


@scenario
def accident_worklist_fuzzy(M):
    acc = _accident(M, case="CAS999/01/2020", parties=["P_1"],
                    sources={"EMS": "c1", "HOSPITAL": "c2"})
    return _std(M, _claim(M, case_number_raw=None), accidents=[acc])


@scenario
def accident_created(M):
    return _std(M, _claim(M, case_number_raw=None), accidents=[])


@scenario
def claimant_surge(M):
    acc = _accident(M, parties=["P_1", "P_2"], oar=1,
                    sources={"EMS": "c1", "HOSPITAL": "c2", "SAPS": "c3"})
    return _std(M, _claim(M), accidents=[acc])


@scenario
def convergence_thin(M):
    acc = _accident(M, parties=["P_1"], oar=5, sources={"SAPS": "c1"})
    return _std(M, _claim(M), accidents=[acc])


@scenario
def convergence_cluster_collapse(M):
    # EMS and HOSPITAL share one party-cluster -> collapse to a single vote
    acc = _accident(M, parties=["P_1"], oar=5,
                    sources={"EMS": "ring1", "HOSPITAL": "ring1", "INDEPENDENT_CLAIMANT": "c9"})
    return _std(M, _claim(M), accidents=[acc])


# ── 2026-11-09 review, High findings (H1-H8, H12) ─────────────────────────────
# Each scenario here pins a behavioural change made oracle-first; the conformance test proves
# the modular engine reproduces it, the unit tests assert the concrete values.

# H1 — prescription clocks count calendar years, not 365-day blocks
@scenario
def h1_three_calendar_years_spanning_leap_day_not_prescribed(M):
    # 2024-03-01 + 3 calendar years = 2027-03-01 (1096 days; 365*3 would have expired 02-28)
    return _std(M, _claim(M, ctype="PERSONAL", merits_accepted=True,
                          accident_date=date(2024, 3, 1), lodged_on=date(2027, 3, 1)))


@scenario
def h1_day_after_third_anniversary_prescribed(M):
    return _std(M, _claim(M, ctype="PERSONAL", merits_accepted=True,
                          accident_date=date(2024, 3, 1), lodged_on=date(2027, 3, 2)))


@scenario
def h1_leap_day_accident_anniversary_falls_to_first_of_march(M):
    # accident 29 Feb 2024: no 29 Feb 2027 -> anniversary 1 Mar 2027; lodging that day is in time
    return _std(M, _claim(M, ctype="PERSONAL", merits_accepted=True,
                          accident_date=date(2024, 2, 29), lodged_on=date(2027, 3, 1)))


@scenario
def h1_summons_five_calendar_years(M):
    # lodged 2026-03-01 + 5y = 2031-03-01; served on the anniversary is in time (strict >)
    return _std(M, _claim(M, ctype="PERSONAL", merits_accepted=True),
                summons_served=date(2031, 3, 1))


# H2 — the cross-claim pay-once ledger (s17(5)) and one claim per claimant per accident
@scenario
def h2_cross_claim_line_supplier_preclusion(M):
    # the same service was already paid on another claim for this party -> SUPPLIER_PRECLUSION
    prior = {M.line_key("P_1", _line(M))}
    return _std(M, _claim(M, lines=[_line(M), _line(M, amount=300.0)]), seen_lines=prior)


@scenario
def h2_duplicate_personal_claim_same_claimant_same_accident(M):
    acc = _accident(M, parties=["P_1"], oar=5, claimants=["P_1"],
                    sources={"EMS": "c1", "HOSPITAL": "c2", "SAPS": "c3"})
    return _std(M, _claim(M, ctype="PERSONAL", merits_accepted=True), accidents=[acc])


@scenario
def h2_supplier_claim_for_an_existing_claimant_is_not_a_duplicate_claim(M):
    acc = _accident(M, parties=["P_1"], oar=5, claimants=["P_1"],
                    sources={"EMS": "c1", "HOSPITAL": "c2", "SAPS": "c3"})
    return _std(M, _claim(M), accidents=[acc])


# H3 — one code identity: leading zeros never separate two codes
@scenario
def h3_leading_zero_cannot_bypass_preauth(M):
    u = _undertaking(M, scope=("S72",), coded=True, auths=[])
    return _std(M, _claim(M, ctype="UNDERTAKING_INVOICE",
                          lines=[_line(M, code="500", amount=500.0, dx="S72")], undertaking=u))


@scenario
def h3_leading_zero_variants_are_one_duplicate_line(M):
    return _std(M, _claim(M, lines=[_line(M, code="0190", amount=500.0),
                                    _line(M, code="190", amount=500.0)]))


@scenario
def h3_leading_zero_non_benchmarkable_still_unresolved(M):
    return _std(M, _claim(M, lines=[_line(M, code="11", amount=500.0)]))


@scenario
def h3_authorisation_matches_normalised_code(M):
    u = _undertaking(M, scope=("S72",), coded=True, auths=[_auth(M, codes=("190",), ceiling=1000.0)])
    return _std(M, _claim(M, ctype="UNDERTAKING_INVOICE",
                          lines=[_line(M, code="0190", amount=500.0, dx="S72")], undertaking=u))


# H4 — an authorisation is a finite promise: the ceiling and qty_limit are consumed across lines
@scenario
def h4_ceiling_consumed_across_lines(M):
    u = _undertaking(M, scope=("S72",), coded=True, auths=[_auth(M, codes=("0190",), ceiling=1000.0)])
    return _std(M, _claim(M, ctype="UNDERTAKING_INVOICE", undertaking=u,
                          lines=[_line(M, code="0190", amount=999.0, dx="S72"),
                                 _line(M, code="0190", amount=998.0, dx="S72"),
                                 _line(M, code="0190", amount=997.0, dx="S72")]))


@scenario
def h4_qty_limit_consumed_across_lines(M):
    # 3 units authorised: line 1 uses 2 (R200), line 2 asks 2 @ R100/unit -> 1 unit (R100)
    u = _undertaking(M, scope=("S72",), coded=True,
                     auths=[_auth(M, codes=("0190",), qty=3.0, ceiling=10000.0)])
    return _std(M, _claim(M, ctype="UNDERTAKING_INVOICE", undertaking=u,
                          lines=[_line(M, code="0190", qty=2.0, amount=200.0, dx="S72"),
                                 _line(M, code="0190", qty=2.0, amount=200.0, dx="S72",
                                       svc=date(2026, 3, 2))]))


# H5 — ADVISORY signals and GREEN-band heuristics never route a claim
@scenario
def h5_advisory_override_is_visible_but_not_dispositive(M):
    return _std(M, _claim(M, lines=[_line(M, dx="K35")]), accident_dx_regions={"S72"},
                mode_overrides={"DX_ACCIDENT_MISMATCH": M.SignalMode.ADVISORY})


@scenario
def h5_single_green_heuristic_stays_clean_and_payable(M):
    # (same inputs as dx_accident_mismatch: 15 points, GREEN -> informational, not FRAUD)
    return _std(M, _claim(M, lines=[_line(M, dx="K35")]), accident_dx_regions={"S72"})


# H6 — an uncovered code is a hard REVIEW gate, not paid as billed
@scenario
def h6_uncovered_code_billed_absurdly_is_held_for_review(M):
    return _std(M, _claim(M, lines=[_line(M, code="7777", amount=1_000_000_000_000.0)]))


# H8 — Grounded gates cannot be shadowed; a non-enum override value is ignored
@scenario
def h8_grounded_gate_shadow_override_ignored(M):
    return _std(M, _claim(M, ctype="PERSONAL", merits_accepted=True,
                          accident_date=date(2020, 1, 1), lodged_on=date(2024, 1, 1)),
                mode_overrides={"PRESCRIBED_LODGEMENT": M.SignalMode.SHADOW})


@scenario
def h8_non_enum_override_value_falls_back_to_default(M):
    return _std(M, _claim(M, lines=[_line(M, dx="K35")]), accident_dx_regions={"S72"},
                mode_overrides={"DX_ACCIDENT_MISMATCH": "SHADOW"})


@scenario
def h8_unvalidated_signal_promoted_to_scored(M):
    return _std(M, _claim(M, case_number_raw=None), accidents=[],
                mode_overrides={"CONVERGENCE_THIN": M.SignalMode.SCORED})


# H12 — money is exact: Decimal half-up at the engine boundary
@scenario
def h12_apportionment_rounds_half_up(M):
    # R100.05 at 30% fault = R70.035 -> R70.04 (binary float rounding gave R70.03)
    return _std(M, _claim(M, ctype="PERSONAL", merits_accepted=True, fault_pct=30.0,
                          lines=[_line(M, amount=100.05)]))


@scenario
def h12_nappi_fee_and_qty_pricing_exact(M):
    # SEP 88.40 + 30% fee (26.52) = 114.92; qty 3 -> 344.76 expected, billed 344.77 -> repriced
    return _std(M, _claim(M, lines=[_line(M, kind="NAPPI", code="700101", qty=3.0, amount=344.77)]))


# dated reference versions — the rate in force on the SERVICE date (port of CIE's rate store) ----
def _dated_book(M):
    b = _book(M)
    b.rpl["190"] = {"GP": [(date(2020, 1, 1), date(2025, 12, 31), 400.0), (date(2026, 1, 1), None, 500.0)],
                    "SPECIALIST": 700.0}
    b.rpl["23"] = {"GP": [(date(2026, 3, 1), None, 100.0)]}                 # no rate before March 2026
    b.rpl["55"] = {"GP": 380.0}
    b.negotiated[("TARIFF", "55")] = [(date(2026, 1, 1), date(2026, 2, 28), 400.0)]   # contract ended
    b.sep["700101"] = [(date(2020, 1, 1), date(2026, 2, 28), 80.0), (date(2026, 3, 1), None, 88.40)]
    return b


def _dated(M, c, **kw):
    return dict(c=c, accidents=[], book=_dated_book(M), rs=_rs(M), today=TODAY, **kw)


def _late(M, lines):
    return _claim(M, accident_date=date(2025, 6, 1), lodged_on=date(2026, 3, 1), lines=lines)


@scenario
def d1_late_claim_prices_at_the_rate_in_force_on_its_service_date(M):
    return _dated(M, _late(M, [_line(M, code="0190", amount=500.0, svc=date(2025, 7, 1))]))


@scenario
def d1_same_bill_after_the_increase_is_clean(M):
    return _dated(M, _late(M, [_line(M, code="0190", amount=500.0, svc=date(2026, 3, 1))]))


@scenario
def d1_lines_straddling_an_increase_price_separately(M):
    return _dated(M, _late(M, [_line(M, code="0190", amount=500.0, svc=date(2025, 12, 31)),
                               _line(M, code="0190", amount=500.0, svc=date(2026, 1, 1))]))


@scenario
def d1_under_the_old_rate_is_paid_as_billed_never_raised(M):
    return _dated(M, _late(M, [_line(M, code="0190", amount=350.0, svc=date(2025, 7, 1))]))


@scenario
def d1_no_version_in_force_on_the_service_date_is_unresolved(M):
    return _dated(M, _claim(M, lines=[_line(M, code="0023", amount=100.0, svc=date(2026, 2, 15))]))


@scenario
def d1_negotiated_rate_applies_while_the_contract_runs(M):
    return _dated(M, _claim(M, lines=[_line(M, code="0055", amount=450.0, svc=date(2026, 2, 15))]))


@scenario
def d1_expired_negotiated_rate_falls_back_to_the_tariff(M):
    return _dated(M, _claim(M, lines=[_line(M, code="0055", amount=450.0, svc=date(2026, 3, 10))]))


@scenario
def d1_nappi_priced_at_the_exit_price_of_its_day(M):
    return _dated(M, _claim(M, lines=[
        _line(M, kind="NAPPI", code="700101", amount=114.92, svc=date(2026, 2, 10)),
        _line(M, kind="NAPPI", code="700101", amount=114.92, svc=date(2026, 3, 2))]))


@scenario
def d1_undated_sibling_discipline_is_unaffected(M):
    return _dated(M, _late(M, [_line(M, code="0190", amount=700.0, svc=date(2025, 7, 1),
                                     discipline="SPECIALIST")]))


# coding rules — what the tariff itself says about a code (port of CIE's coding rules) --------
def _coded_book(M):
    return M.RefBook(
        negotiated={}, raf2022={}, empirical={}, sep={"700101": 88.40}, non_benchmarkable=set(),
        rpl={"190": {"GP": 500.0}, "207": {"GP": 280.0}, "11": {"GP": 400.0}, "23": {"GP": 300.0},
             "39": {"GP": 450.0}},
        # keys are given as billed ("0207") — the book normalises them like every other code
        code_rules={"0207": (M.ONCE_PER_ENCOUNTER, 0.0), "0011": (M.TIME_BLOCK, 30.0),
                    "0012": (M.TIME_BLOCK, 0.0), "0023": (M.TIME_ANAES, 0.0),
                    "0039": (M.TIME_FIRST_HOUR, 0.0), "0040": (M.TIME_FIRST_HOUR, 0.0),
                    "0018": (M.PCT_OF_TIME, 0.5)},
    )


def _coded(M, c, **kw):
    return dict(c=c, accidents=[], book=_coded_book(M), rs=_rs(M), today=TODAY, **kw)


@scenario
def c2_once_only_code_billed_twice_on_one_encounter_pays_the_first(M):
    return _coded(M, _claim(M, lines=[_line(M, code="0207", amount=280.0),
                                      _line(M, code="0207", amount=260.0)]))


@scenario
def c2_once_only_code_on_two_days_is_two_encounters(M):
    return _coded(M, _claim(M, lines=[_line(M, code="0207", amount=280.0),
                                      _line(M, code="0207", amount=260.0, svc=date(2026, 3, 2))]))


@scenario
def c2_once_only_code_by_two_providers_is_two_encounters(M):
    return _coded(M, _claim(M, lines=[_line(M, code="0207", amount=280.0),
                                      _line(M, code="0207", amount=260.0, provider="PR2")]))


@scenario
def c2_once_only_code_already_paid_on_another_claim_is_refused(M):
    paid = {("ONCE", "P_1", "PR1", date(2026, 3, 1), "207")}
    return _coded(M, _claim(M, lines=[_line(M, code="207", amount=250.0)]), seen_lines=paid)


@scenario
def c2_exact_repeat_of_a_once_only_code_is_a_duplicate_line_first(M):
    return _coded(M, _claim(M, lines=[_line(M, code="0207", amount=280.0),
                                      _line(M, code="0207", amount=280.0)]))


@scenario
def c2_time_block_prices_minutes_by_the_half_hour_or_part(M):
    # 45 minutes = 2 blocks x R400 = R800; billed R1,000 -> repriced
    return _coded(M, _claim(M, lines=[_line(M, code="0011", qty=45.0, amount=1000.0)]))


@scenario
def c2_time_block_at_the_ladder_total_is_clean(M):
    return _coded(M, _claim(M, lines=[_line(M, code="0011", qty=60.0, amount=800.0)]))


@scenario
def c2_anaesthetic_time_steps_up_after_the_first_hour(M):
    # 75 minutes = 4 x R300 + 1 x R450 = R1,650; billed R2,000 -> repriced
    return _coded(M, _claim(M, lines=[_line(M, code="0023", qty=75.0, amount=2000.0)]))


@scenario
def c2_anaesthetic_time_within_the_hour(M):
    # 31 minutes = 3 blocks (or part thereof) x R300 = R900
    return _coded(M, _claim(M, lines=[_line(M, code="0023", qty=31.0, amount=900.0)]))


@scenario
def c2_first_hour_rule_adds_a_third_per_quarter_hour(M):
    # 90 minutes = R450 + 2 x R150 = R750; and 20 minutes is still the first-hour block (R450)
    return _coded(M, _claim(M, lines=[_line(M, code="0039", qty=90.0, amount=760.0),
                                      _line(M, code="0039", qty=20.0, amount=450.0,
                                            svc=date(2026, 3, 2))]))


@scenario
def c2_percentage_of_time_is_a_share_of_the_time_line_billed_with_it(M):
    # 0023 for 75 min -> R1,650; 0018 adds 50% = R825; billed R900 -> repriced
    return _coded(M, _claim(M, lines=[_line(M, code="0023", qty=75.0, amount=1650.0),
                                      _line(M, code="0018", amount=900.0)]))


@scenario
def c2_percentage_of_time_with_no_time_line_goes_to_review(M):
    return _coded(M, _claim(M, lines=[_line(M, code="0190"), _line(M, code="0018", amount=300.0)]))


@scenario
def c2_percentage_of_time_ignores_another_day_and_an_unpriced_time_line(M):
    # the 0023 line is another day; the 0040 line has a time rule but no rate -> nothing to share
    return _coded(M, _claim(M, lines=[_line(M, code="0023", qty=30.0, amount=600.0, svc=date(2026, 3, 2)),
                                      _line(M, code="0040", qty=30.0, amount=100.0),
                                      _line(M, code="0018", amount=300.0)]))


@scenario
def c2_time_block_without_a_length_defaults_to_the_half_hour(M):
    b = _coded_book(M)
    b.rpl["12"] = {"GP": 400.0}
    return dict(c=_claim(M, lines=[_line(M, code="0012", qty=31.0, amount=900.0)]),
                accidents=[], book=b, rs=_rs(M), today=TODAY)


# billing signals — encounter-shaped screens (port of CIE's scorer signals) --------------------
def _many(M, n, kind="TARIFF", code="0190", start=0):
    return [_line(M, kind=kind, code=code, amount=100.0 + start + i) for i in range(n)]


def _week_of_visits(M, days):
    return [_line(M, amount=400.0, svc=date(2026, 3, d)) for d in days]


@scenario
def b1_twelve_lines_on_one_encounter_is_a_line_count_outlier(M):
    return _std(M, _claim(M, lines=_many(M, 12)))


@scenario
def b1_eleven_lines_on_one_encounter_is_not(M):
    return _std(M, _claim(M, lines=_many(M, 11)))


@scenario
def b1_twelve_lines_over_two_days_is_two_ordinary_encounters(M):
    lines = _many(M, 6) + [_line(M, amount=200.0 + i, svc=date(2026, 3, 2)) for i in range(6)]
    return _std(M, _claim(M, lines=lines))


@scenario
def b1_consumables_forming_most_of_an_encounter_is_material_padding(M):
    # 12 NAPPI of 15 lines (80%) -> MATERIAL_PADDING + LINE_COUNT_OUTLIER, both advisory at launch
    return _std(M, _claim(M, lines=_many(M, 12, kind="NAPPI", code="700101") + _many(M, 3)))


@scenario
def b1_many_consumables_under_the_share_is_not_padding(M):
    # 12 NAPPI of 21 lines (57%) -> below the 60% share
    return _std(M, _claim(M, lines=_many(M, 12, kind="NAPPI", code="700101") + _many(M, 9)))


@scenario
def b1_provider_billing_thirty_claimants_in_a_day_is_an_impossible_day(M):
    act = M.Activity(provider_day={("PR1", date(2026, 3, 1)): 29})
    return _std(M, _claim(M), activity=act)


@scenario
def b1_twenty_nine_claimants_in_a_day_is_not(M):
    act = M.Activity(provider_day={("PR1", date(2026, 3, 1)): 28, ("PR1", date(2026, 3, 2)): 99})
    return _std(M, _claim(M), activity=act)


@scenario
def b1_hospital_account_is_exempt_from_the_day_and_week_screens(M):
    act = M.Activity(provider_day={("PR1", date(2026, 3, 1)): 500},
                     claimant_encounters={("PR9", date(2026, 3, d)) for d in range(2, 9)})
    return _std(M, _claim(M, facility=True), activity=act)


@scenario
def b1_eight_encounters_in_one_week_is_an_impossible_week(M):
    # 2-8 March 2026 is one ISO week (Monday to Sunday): 3 visits here + 5 on other claims
    act = M.Activity(claimant_encounters={("PR2", date(2026, 3, d)) for d in (2, 3, 4, 5, 6)})
    return _std(M, _claim(M, lines=_week_of_visits(M, (6, 7, 8))), activity=act)


@scenario
def b1_same_encounter_on_two_claims_counts_once(M):
    # the other claim's encounters are this claim's own provider and days -> still 3, not 6
    act = M.Activity(claimant_encounters={("PR1", date(2026, 3, d)) for d in (6, 7, 8)})
    return _std(M, _claim(M, lines=_week_of_visits(M, (6, 7, 8))), activity=act)


@scenario
def b1_visits_spread_over_two_weeks_are_not_an_impossible_week(M):
    act = M.Activity(claimant_encounters={("PR2", date(2026, 3, d)) for d in (9, 10, 11, 12, 13)})
    return _std(M, _claim(M, lines=_week_of_visits(M, (6, 7, 8))), activity=act)


@scenario
def b1_three_same_discipline_providers_is_shopping_in_shadow(M):
    act = M.Activity(claimant_providers={"GP": {"PR2", "PR3"}, "Physiotherapy": {"PT1"}})
    return _std(M, _claim(M), activity=act)


@scenario
def b1_provider_shopping_promoted_to_scored_bands_amber(M):
    act = M.Activity(claimant_providers={"GP": {"PR2", "PR3"}})
    return _std(M, _claim(M), activity=act,
                mode_overrides={"PROVIDER_SHOPPING": M.SignalMode.SCORED})


@scenario
def b1_a_care_team_of_different_disciplines_is_not_shopping(M):
    act = M.Activity(claimant_providers={"Physiotherapy": {"PT1", "PT2", "PT3"}, "GP": {"PR2"}})
    return _std(M, _claim(M), activity=act,
                mode_overrides={"PROVIDER_SHOPPING": M.SignalMode.SCORED})


@scenario
def b1_assigned_disciplines_can_never_be_shopping(M):
    lines = [_line(M, provider=p, discipline="Radiology", amount=400.0) for p in ("RA1", "RA2", "RA3")]
    return _std(M, _claim(M, lines=lines), mode_overrides={"PROVIDER_SHOPPING": M.SignalMode.SCORED})


@scenario
def b1_a_claim_with_no_lines_raises_no_billing_signal(M):
    return _std(M, _claim(M, lines=[]), activity=M.Activity())


# the billing signals launch ADVISORY; an ADMIN promotion makes them score (§11)
def _promoted(M, *codes):
    return {code: M.SignalMode.SCORED for code in codes}


@scenario
def b2_promoted_padding_and_line_count_band_amber(M):
    # MATERIAL_PADDING 15 + LINE_COUNT_OUTLIER 15 (endogenous) = 30 points
    return _std(M, _claim(M, lines=_many(M, 12, kind="NAPPI", code="700101") + _many(M, 3)),
                mode_overrides=_promoted(M, "MATERIAL_PADDING", "LINE_COUNT_OUTLIER"))


@scenario
def b2_promoted_impossible_day_alone_routes_to_fraud_review(M):
    act = M.Activity(provider_day={("PR1", date(2026, 3, 1)): 29})
    return _std(M, _claim(M), activity=act, mode_overrides=_promoted(M, "IMPOSSIBLE_DAY"))


@scenario
def b2_promoted_impossible_week_scores_but_stays_green_alone(M):
    act = M.Activity(claimant_encounters={("PR2", date(2026, 3, d)) for d in (2, 3, 4, 5, 6)})
    return _std(M, _claim(M, lines=_week_of_visits(M, (6, 7, 8))), activity=act,
                mode_overrides=_promoted(M, "IMPOSSIBLE_WEEK"))
