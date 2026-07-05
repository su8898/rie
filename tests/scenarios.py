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
    # "0190"->"190"); NAPPI codes and the non-benchmarkable set key on the raw code.
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
              sources=None, where="", vehicles=None):
    return M.Accident(accident_id="A_pre", case_number=case, when=when, where=where,
                      vehicles=set(vehicles or []), parties=set(parties or ["P_1"]),
                      oar_occupants=oar, sources=dict(sources or {}))


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
