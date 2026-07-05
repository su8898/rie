"""
RIE — the engine ("the brain"), as one readable algorithm.

This is the complete decision path of the RAF Integrity Engine, expressed as
deterministic, side-effect-free Python. It is NOT the system (no web, no DB,
no workers) — it is the algorithm the system exists to run. Every section is
cross-referenced to domain-logic.md (§n).

Pipeline:  raw claim ─► canonicalise ─► resolve accident (§6.0) ─► corroborate (§6.0)
           ─► compliance gates (§4) ─► merits gate (§4c) ─► per-line adjudication (§3, §5f)
           ─► heads of damage (§5) ─► score + band (§10, §11) ─► disposition (§9)
           ─► payment eligibility (§8e)

Design invariants (CIE doctrine):
  * One shared ReferenceResolver — every rand agrees across surfaces.
  * Hard gates never come from statistics; statistical signals never auto-reject.
  * Endogenous signals are n-guarded and capped below RED.
  * Signal modes (SHADOW/ADVISORY/SCORED) make calibration governance, not guesswork.
  * Every determination is reproducible: rules read the ruleset & reference editions
    effective at the relevant date, and the output carries provenance.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum, auto
from typing import Optional

# ────────────────────────────────────────────────────────────────────────────
# 0. VOCABULARY — enums, reason registry, constants                     (§10)
# ────────────────────────────────────────────────────────────────────────────

class LegalStatus(Enum):          # §3 — benchmark sources carry legal status
    ENFORCEABLE = auto()          # negotiated rates, SEP+fee, authorisations
    ACCEPTED = auto()             # RPL — provider-accepted market rate
    INTERDICTED = auto()          # RAF 2022 tariff — signal only
    ENDOGENOUS = auto()           # empirical medians — signal only

PAYMENT_RULE_STATUSES = {LegalStatus.ENFORCEABLE, LegalStatus.ACCEPTED}

class Maturity(Enum):             # §1 — defensibility layer
    GROUNDED = auto()             # statute / case law / regulation cited
    HEURISTIC = auto()            # reasonable rule, stated weakness
    UNVALIDATED = auto()          # not yet calibrated

class SignalMode(Enum):           # §11 — promotion lifecycle
    SHADOW = auto()               # computed, stored, zero points, invisible
    ADVISORY = auto()             # visible, zero points
    SCORED = auto()               # contributes to band

class Category(Enum):             # §9 — disposition, worst-first
    FRAUD = 1
    MERITS = 2
    COMPLIANCE = 3
    PREAUTH = 4
    SI_GATE = 5
    ADJUSTED = 6
    CLEAN = 7

class Band(Enum):
    GREEN = auto(); AMBER = auto(); RED = auto()

AMBER_AT, RED_AT = 25, 50
ENDOGENOUS_POINT_CAP = 45         # endogenous signals alone can never reach RED (§10)

@dataclass(frozen=True)
class ReasonMeta:
    category: Category
    hard: bool                    # hard gate vs soft feature
    points: int                   # soft-feature score contribution when SCORED
    maturity: Maturity
    endogenous: bool = False      # counts toward the endogenous cap
    basis: str = ""               # citation or stated weakness

R = {  # the reason-code catalogue (§10) — abridged bases
    # HARD gates — Grounded
    "PRESCRIBED_LODGEMENT":   ReasonMeta(Category.COMPLIANCE, True, 0, Maturity.GROUNDED, basis="s23"),
    "PRESCRIBED_SUMMONS":     ReasonMeta(Category.COMPLIANCE, True, 0, Maturity.GROUNDED, basis="s23(3)"),
    "S24_INCOMPLETE":         ReasonMeta(Category.COMPLIANCE, True, 0, Maturity.GROUNDED, basis="s24"),
    "OAR_MISSING":            ReasonMeta(Category.COMPLIANCE, True, 0, Maturity.GROUNDED, basis="s24 + reg"),
    "DUPLICATE_CLAIM":        ReasonMeta(Category.COMPLIANCE, True, 0, Maturity.GROUNDED, basis="one claim per claimant per accident"),
    "PROVIDER_UNREGISTERED":  ReasonMeta(Category.COMPLIANCE, True, 0, Maturity.GROUNDED, basis="HPCSA/BHF register"),
    "ATTORNEY_NOT_IN_STANDING":ReasonMeta(Category.COMPLIANCE, True, 0, Maturity.GROUNDED, basis="LPC register (payment hold)"),
    "PAYEE_UNVERIFIED":       ReasonMeta(Category.COMPLIANCE, True, 0, Maturity.GROUNDED, basis="AVS"),
    "LIFE_STATUS_MISMATCH":   ReasonMeta(Category.COMPLIANCE, True, 0, Maturity.GROUNDED, basis="DHA / death certificate (§5g)"),
    "SOLE_NEGLIGENCE":        ReasonMeta(Category.MERITS,     True, 0, Maturity.GROUNDED, basis="s17(1)"),
    "S19_EXCLUSION":          ReasonMeta(Category.MERITS,     True, 0, Maturity.GROUNDED, basis="s19"),
    "NO_MVA_NEXUS":           ReasonMeta(Category.MERITS,     True, 0, Maturity.GROUNDED, basis="s17(1) driving nexus"),
    "SERVICE_BEFORE_ACCIDENT":ReasonMeta(Category.COMPLIANCE, True, 0, Maturity.GROUNDED, basis="date CHECK"),
    "SUPPLIER_PRECLUSION":    ReasonMeta(Category.ADJUSTED,   True, 0, Maturity.GROUNDED, basis="s17(5) — pay once"),
    "DUPLICATE_LINE":         ReasonMeta(Category.ADJUSTED,   True, 0, Maturity.GROUNDED, basis="pay first occurrence"),
    "PREAUTH_MISSING":        ReasonMeta(Category.PREAUTH,    True, 0, Maturity.GROUNDED, basis="§5f ruleset"),
    "PREAUTH_EXCEEDED":       ReasonMeta(Category.ADJUSTED,   True, 0, Maturity.GROUNDED, basis="§5f — reprice to ceiling"),
    "UNDERTAKING_NOT_ACTIVE": ReasonMeta(Category.COMPLIANCE, True, 0, Maturity.GROUNDED, basis="s17(4)(a)"),
    "UNDERTAKING_SCOPE":      ReasonMeta(Category.COMPLIANCE, True, 0, Maturity.GROUNDED, basis="undertaking terms (soft if uncoded)"),
    "GENERAL_DAMAGES_NO_SI":  ReasonMeta(Category.SI_GATE,    True, 0, Maturity.GROUNDED, basis="reg 3 / RAF 4"),
    "EARNINGS_UNPROVEN":      ReasonMeta(Category.COMPLIANCE, True, 0, Maturity.GROUNDED, basis="proof requirement"),
    # Soft features
    "BILLED_OVER_REFERENCE":  ReasonMeta(Category.ADJUSTED,   False,  0, Maturity.GROUNDED, basis="repriced when enforceable/accepted; else signal"),
    "VALUE_OUTLIER":          ReasonMeta(Category.FRAUD, False, 15, Maturity.HEURISTIC, endogenous=True, basis="condition band p90"),
    "VALUE_OUTLIER_EXTREME":  ReasonMeta(Category.FRAUD, False, 30, Maturity.HEURISTIC, endogenous=True, basis="condition band, extreme"),
    "LINE_COUNT_OUTLIER":     ReasonMeta(Category.FRAUD, False, 15, Maturity.HEURISTIC, endogenous=True, basis="corpus percentile"),
    "MATERIAL_PADDING":       ReasonMeta(Category.FRAUD, False, 15, Maturity.HEURISTIC, basis="NAPPI-dominated encounter"),
    "IMPOSSIBLE_DAY":         ReasonMeta(Category.FRAUD, False, 25, Maturity.HEURISTIC, basis="billed minutes > plausible day"),
    "DX_ACCIDENT_MISMATCH":   ReasonMeta(Category.FRAUD, False, 15, Maturity.HEURISTIC, basis="body region vs accident profile"),
    "PRE_EXISTING_CONDITION": ReasonMeta(Category.COMPLIANCE, False, 5, Maturity.HEURISTIC, basis="review — aggravation compensable"),
    "INJURY_ESCALATION":      ReasonMeta(Category.FRAUD, False, 15, Maturity.HEURISTIC, basis="RAF1/4 vs first-contact records"),
    "OAR_MISMATCH":           ReasonMeta(Category.FRAUD, False,  5, Maturity.HEURISTIC, basis="SAPS data quality (LOW, never sole ground)"),
    "OAR_REUSED":             ReasonMeta(Category.FRAUD, False, 15, Maturity.HEURISTIC, basis="conflicting accident records, one CAS"),
    "EARNINGS_OUTLIER":       ReasonMeta(Category.FRAUD, False, 10, Maturity.HEURISTIC, endogenous=True, basis="sector band"),
    "LATE_CLAIM_CLUSTER":     ReasonMeta(Category.FRAUD, False, 15, Maturity.HEURISTIC, basis="deadline clustering"),
    # Graph / collusion — launch in SHADOW (§11)
    "RING_PARTIES":           ReasonMeta(Category.FRAUD, False, 25, Maturity.UNVALIDATED, basis="party-graph recurrence"),
    "CLAIMANT_SURGE":         ReasonMeta(Category.FRAUD, False, 20, Maturity.UNVALIDATED, basis="claimants vs capacity, cohort-aware"),
    "CLAIMANT_RECURRENCE":    ReasonMeta(Category.FRAUD, False, 15, Maturity.UNVALIDATED, basis="P_* across accidents"),
    "CONVERGENCE_THIN":       ReasonMeta(Category.FRAUD, False, 20, Maturity.UNVALIDATED, basis="evidence density/timing (§6.0)"),
}

# Live signal modes — reference data, not code (§11). Defaults at launch:
MODE: dict[str, SignalMode] = {
    code: (SignalMode.SHADOW if meta.maturity is Maturity.UNVALIDATED else SignalMode.SCORED)
    for code, meta in R.items()
}

# ────────────────────────────────────────────────────────────────────────────
# 1. DATA SHAPES (minimal — the algorithm's view of the world)          (§2)
# ────────────────────────────────────────────────────────────────────────────

@dataclass
class Ruleset:                    # effective at accident date (§1)
    lodgement_years_identified: int = 3
    lodgement_years_hitrun: int = 2
    summons_years: int = 5
    investigation_days: int = 120
    wpi_threshold: float = 30.0
    caps: list[tuple[date, float]] = field(default_factory=list)   # (effective_from, annual_cap)
    preauth_required: set[str] = field(default_factory=set)        # code classes needing pre-auth
    s19_grounds: set[str] = field(default_factory=set)

    def cap_at(self, accident_date: date) -> float:                # §5c — Sweatman/s17(4A)(b)
        rows = [c for eff, c in sorted(self.caps) if eff <= accident_date]
        return rows[-1] if rows else 0.0

@dataclass
class Line:
    kind: str                     # 'TARIFF' | 'NAPPI'
    code: str
    qty: float
    amount: float                 # billed, rand
    service_date: date
    provider_id: str
    dx: str                       # ICD-10 on the line
    emergency: bool = False
    scheme_paid: bool = False

@dataclass
class Authorisation:              # §5f — a promise priced in advance
    codes: set[str]
    qty_limit: float
    ceiling: float                # rand
    valid_from: date
    valid_to: date
    status: str = "APPROVED"

@dataclass
class Undertaking:                # §8c
    active: bool
    scope_dx: set[str]            # ICD-10 set (3-char compared)
    scope_coded: bool
    authorisations: list[Authorisation] = field(default_factory=list)

@dataclass
class Claim:
    claim_id: str
    claim_type: str               # PERSONAL | SUPPLIER | UNDERTAKING_INVOICE
    party_token: str
    accident_date: date
    lodged_on: date
    case_number_raw: Optional[str]
    documents: dict[str, bool]    # s24 checklist (§4b)
    lines: list[Line]
    heads: dict[str, dict] = field(default_factory=dict)   # head → inputs
    hit_and_run: bool = False
    prescription_suspended: bool = False
    fault_pct: Optional[float] = None       # merits determination, 0..100
    merits_accepted: Optional[bool] = None
    merits_ground: Optional[str] = None
    si_accepted: Optional[bool] = None      # RAF 4 outcome (§8b)
    undertaking: Optional[Undertaking] = None
    claimant_deceased_on: Optional[date] = None
    payee_verified: bool = False
    attorney_in_standing: bool = True
    provider_registered: bool = True

@dataclass
class Accident:                   # §6.0
    accident_id: str
    case_number: Optional[str]
    when: date
    where: str
    vehicles: set[str]
    parties: set[str]
    oar_occupants: Optional[int]
    sources: dict[str, str] = field(default_factory=dict)  # source_class → cluster_id
    claims: list[str] = field(default_factory=list)

# ────────────────────────────────────────────────────────────────────────────
# 2. ACCIDENT ENTITY RESOLUTION                                        (§6.0)
# ────────────────────────────────────────────────────────────────────────────

AUTO_JOIN, WORKLIST = 0.85, 0.50

def normalise_cas(raw: Optional[str]) -> Optional[str]:
    """CAS 123/04/2026 · 123/4/26 · cas123-4-2026 → 'CAS123/04/2026'."""
    if not raw:
        return None
    digits = [t for t in "".join(c if c.isdigit() else " " for c in raw).split() if t]
    if len(digits) < 3:
        return None
    n, m, y = digits[0], digits[1].zfill(2), digits[2]
    y = ("20" + y) if len(y) == 2 else y
    return f"CAS{int(n)}/{m}/{y}"

def match_score(c: Claim, a: Accident, place: str, vehicles: set[str]) -> float:
    s = 0.0
    s += 0.40 if abs((c.accident_date - a.when).days) <= 1 else 0.0
    s += 0.20 if place and place == a.where else 0.0
    s += 0.25 if vehicles & a.vehicles else 0.0
    s += 0.15 if c.party_token in a.parties else 0.0
    return s

def resolve_accident(c: Claim, accidents: list[Accident],
                     place: str = "", vehicles: set[str] = frozenset()) -> tuple[Accident, str]:
    """Returns (accident, action) — action ∈ JOINED | AUTO_JOINED | WORKLIST | CREATED."""
    cas = normalise_cas(c.case_number_raw)
    if cas:
        for a in accidents:
            if a.case_number == cas:
                return a, "JOINED"
    best, score = None, 0.0
    for a in accidents:                              # blocking: date ± 1 day
        if abs((c.accident_date - a.when).days) <= 1:
            s = match_score(c, a, place, vehicles)
            if s > score:
                best, score = a, s
    if best and score >= AUTO_JOIN:
        return best, "AUTO_JOINED"
    if best and score >= WORKLIST:
        return best, "WORKLIST"                      # human confirms/creates
    a = Accident(f"A_{len(accidents)+1}", cas, c.accident_date, place, set(vehicles),
                 {c.party_token}, None)              # materialised on first touch
    return a, "CREATED"

# ────────────────────────────────────────────────────────────────────────────
# 3. CORROBORATION — convergence as proof                              (§6.0)
# ────────────────────────────────────────────────────────────────────────────

SOURCE_WEIGHT = {  # independence-weighted source classes
    "SAPS": 0.5, "EMS": 2.0, "HOSPITAL": 2.0, "PREAUTH_L3": 2.0,
    "PHARMACY": 1.0, "INDEPENDENT_CLAIMANT": 2.0, "EMPLOYER": 1.0, "INJURY_COHERENCE": 1.5,
}
MAX_CONVERGENCE = sum(SOURCE_WEIGHT.values())

def convergence(a: Accident) -> float:
    """0–100. Sources sharing one party-cluster collapse to a single vote."""
    seen_clusters: dict[str, str] = {}
    total = 0.0
    for source_class, cluster in a.sources.items():
        if cluster in seen_clusters and seen_clusters[cluster] != source_class:
            continue                                  # same attorney/provider network: one vote
        seen_clusters[cluster] = source_class
        total += SOURCE_WEIGHT.get(source_class, 0.5)
    return round(100 * total / MAX_CONVERGENCE, 1)

def corroboration_signals(a: Accident, cohort_is_bus_taxi: bool, conv_floor_p10: float) -> list[str]:
    out = []
    if a.oar_occupants and len(a.parties) > a.oar_occupants and not cohort_is_bus_taxi:
        out.append("CLAIMANT_SURGE")                  # cohort-aware; OAR count = LOW confidence
    if convergence(a) < conv_floor_p10:               # calibrated from the genuine-accident band
        out.append("CONVERGENCE_THIN")
    return out

# ────────────────────────────────────────────────────────────────────────────
# 4. THE BENCHMARK — one resolver, legal status on every answer          (§3)
# ────────────────────────────────────────────────────────────────────────────

GAZETTE_FLOOR, OCR_SUSPECT_RATIO = 10.0, 0.33
DISP_FEE_THRESHOLD, DISP_FEE_PCT, DISP_FEE_FLAT = 155.0, 0.30, 46.50

@dataclass
class RefBook:
    negotiated: dict[tuple[str, str], float]          # (kind, code) → rate
    rpl: dict[str, tuple[float, Optional[float]]]     # code → (gp, specialist)
    raf2022: dict[str, float]                         # discipline-resolved gazette rate
    empirical: dict[tuple[str, str], float]
    sep: dict[str, float]                             # NAPPI → single exit price
    non_benchmarkable: set[str]

def dispensing_fee(sep: float) -> float:
    return round(sep * DISP_FEE_PCT, 2) if sep < DISP_FEE_THRESHOLD else DISP_FEE_FLAT

def resolve(book: RefBook, kind: str, code: str, tier: str = "GP"
            ) -> tuple[Optional[float], str, Optional[LegalStatus]]:
    """→ (rate, src, legal_status). Only ENFORCEABLE/ACCEPTED drive the payment rule."""
    if code in book.non_benchmarkable:
        return None, "—", None
    nc = code.lstrip("0") or "0" if kind == "TARIFF" else code   # normalisation
    if (kind, nc) in book.negotiated:
        return book.negotiated[(kind, nc)], "negotiated", LegalStatus.ENFORCEABLE
    if kind == "TARIFF":
        if nc in book.rpl:
            gp, spec = book.rpl[nc]
            rate = spec if (tier == "SPECIALIST" and spec) else gp
            return rate, "RPL", LegalStatus.ACCEPTED
        if nc in book.raf2022 and book.raf2022[nc] >= GAZETTE_FLOOR:
            g, emp = book.raf2022[nc], book.empirical.get((kind, nc))
            if emp and g < OCR_SUSPECT_RATIO * emp:              # dropped-digit OCR guard
                return emp, "empirical", LegalStatus.ENDOGENOUS
            return g, "RAF 2022", LegalStatus.INTERDICTED
    if kind == "NAPPI" and code in book.sep:
        sep = book.sep[code]
        return round(sep + dispensing_fee(sep), 2), "NAPPI+fee", LegalStatus.ENFORCEABLE
    if (kind, nc) in book.empirical:
        return book.empirical[(kind, nc)], "empirical", LegalStatus.ENDOGENOUS
    return None, "—", None

# ────────────────────────────────────────────────────────────────────────────
# 5. GATES — grounded, hard, cited                                       (§4)
# ────────────────────────────────────────────────────────────────────────────

def prescription_gates(c: Claim, rs: Ruleset, today: date, summons_served: Optional[date]) -> list[str]:
    out = []
    years = rs.lodgement_years_hitrun if c.hit_and_run else rs.lodgement_years_identified
    if not c.prescription_suspended and c.lodged_on > c.accident_date + timedelta(days=365 * years):
        out.append("PRESCRIBED_LODGEMENT")
    if summons_served and summons_served > c.lodged_on + timedelta(days=365 * rs.summons_years):
        out.append("PRESCRIBED_SUMMONS")
    return out

MANDATORY_DOCS = {   # §4b — per claim type (abridged)
    "PERSONAL":            {"RAF1", "OAR", "ID", "BANK"},
    "SUPPLIER":            {"RAF2", "OAR", "INVOICES", "BANK"},
    "UNDERTAKING_INVOICE": {"INVOICES", "BANK"},
}

def s24_gates(c: Claim) -> list[str]:
    missing = MANDATORY_DOCS[c.claim_type] - {k for k, v in c.documents.items() if v}
    out = []
    if "OAR" in missing:
        out.append("OAR_MISSING")                    # universal hard item; OAR_PENDING pre-validation
        missing.discard("OAR")
    if missing:
        out.append("S24_INCOMPLETE")
    return out

def standing_gates(c: Claim, deceased_before_service: bool) -> list[str]:
    out = []
    if not c.provider_registered:  out.append("PROVIDER_UNREGISTERED")
    if not c.attorney_in_standing: out.append("ATTORNEY_NOT_IN_STANDING")   # payment hold
    if deceased_before_service:    out.append("LIFE_STATUS_MISMATCH")       # §5g
    return out

def merits_gate(c: Claim) -> list[str]:
    if c.merits_accepted is False:
        return [c.merits_ground or "S19_EXCLUSION"]   # SOLE_NEGLIGENCE | S19_EXCLUSION | NO_MVA_NEXUS
    return []                                         # None = pending → held_for_merits (not a reason)

# ────────────────────────────────────────────────────────────────────────────
# 6. LINE ADJUDICATION — reconcile, reprice, or refer                (§3, §5f)
# ────────────────────────────────────────────────────────────────────────────

@dataclass
class LineResult:
    payable: float
    reasons: list[str]
    src: str
    needs_review: bool = False

def find_authorisation(u: Optional[Undertaking], line: Line) -> Optional[Authorisation]:
    if not u:
        return None
    for auth in u.authorisations:
        if auth.status == "APPROVED" and line.code in auth.codes \
           and auth.valid_from <= line.service_date <= auth.valid_to:
            return auth
    return None

def adjudicate_line(c: Claim, line: Line, book: RefBook, rs: Ruleset,
                    tier: str, seen: set, accident_dx_regions: set[str]) -> LineResult:
    reasons: list[str] = []

    # 6.1 hard causation/date gates (§4d)
    if line.service_date < c.accident_date:
        return LineResult(0.0, ["SERVICE_BEFORE_ACCIDENT"], "—")
    key = (c.party_token, line.provider_id, line.service_date, line.code, line.amount)
    if key in seen:                                   # §4e/§4f — pay once, across claim types
        return LineResult(0.0, ["DUPLICATE_LINE"], "—")
    seen.add(key)
    if line.dx[:3] not in accident_dx_regions and accident_dx_regions:
        reasons.append("DX_ACCIDENT_MISMATCH")        # soft → review, aggravation compensable

    # 6.2 undertaking + pre-authorisation reconciliation (§5b, §5f)
    if c.claim_type == "UNDERTAKING_INVOICE":
        u = c.undertaking
        if not u or not u.active:
            return LineResult(0.0, ["UNDERTAKING_NOT_ACTIVE"], "—")
        in_scope = line.dx[:3] in {d[:3] for d in u.scope_dx}
        if not in_scope:
            if u.scope_coded:
                return LineResult(0.0, ["UNDERTAKING_SCOPE"], "—")
            reasons.append("UNDERTAKING_SCOPE")       # soft on uncoded legacy scope → review
        auth = find_authorisation(u, line)
        if auth:                                      # the promise priced in advance
            ceiling = min(auth.ceiling, auth.qty_limit and auth.ceiling or auth.ceiling)
            if line.amount > ceiling:
                return LineResult(ceiling, ["PREAUTH_EXCEEDED"], "authorisation")
            return LineResult(line.amount, reasons, "authorisation")
        if line.code in rs.preauth_required and not line.emergency:
            return LineResult(0.0, reasons + ["PREAUTH_MISSING"], "—")

    # 6.3 reference pricing — the payment rule (§3)
    rate, src, status = resolve(book, line.kind, line.code, tier)
    if rate is None:
        return LineResult(line.amount, reasons, src, needs_review=True)   # uncovered → R&N review
    expected = round(rate * line.qty, 2)
    if line.amount > expected:
        reasons.append("BILLED_OVER_REFERENCE")
        if status in PAYMENT_RULE_STATUSES:
            return LineResult(expected, reasons, src)                     # reprice — pay min
        return LineResult(line.amount, reasons, src, needs_review=True)   # signal only (interdicted/endogenous)
    return LineResult(line.amount, reasons, src)      # under/at reference: pay as billed, never raised

# ────────────────────────────────────────────────────────────────────────────
# 7. HEADS OF DAMAGE — gross → apportioned → capped → offer              (§5)
# ────────────────────────────────────────────────────────────────────────────

def apportion(amount: float, fault_pct: Optional[float]) -> float:
    return round(amount * (1 - (fault_pct or 0.0) / 100), 2)

def head_past_medical(line_results: list[LineResult], fault_pct: Optional[float]) -> float:
    return apportion(sum(r.payable for r in line_results), fault_pct)

def head_loss_of_earnings(annual_losses_after_contingency: list[float],
                          c: Claim, rs: Ruleset) -> tuple[float, list[dict]]:
    """§5c — Sweatman: cap each year at the accident-date cap, THEN apportion."""
    cap = rs.cap_at(c.accident_date)
    worksheet = [{"year": i + 1, "loss": loss, "cap": cap, "capped": min(loss, cap)}
                 for i, loss in enumerate(annual_losses_after_contingency)]
    total = apportion(sum(w["capped"] for w in worksheet), c.fault_pct)
    return total, worksheet                           # worksheet stored — litigation-reproducible

def head_general_damages(c: Claim, band_p25: float, band_p75: float,
                         proposed: float) -> tuple[float, list[str]]:
    """§5d — gated by SI (list-first → WPI ≥ 30% → narrative, decided in §8b machinery)."""
    if not c.si_accepted:
        return 0.0, ["GENERAL_DAMAGES_NO_SI"]
    reasons = [] if band_p25 <= proposed <= band_p75 else ["GD_OUTSIDE_BAND_NOTE"]  # note, never a gate
    return apportion(proposed, c.fault_pct), reasons

# ────────────────────────────────────────────────────────────────────────────
# 8. SCORING — reasons → points → band                              (§10, §11)
# ────────────────────────────────────────────────────────────────────────────

@dataclass
class Assessment:
    reasons: list[str]            # SCORED + ADVISORY (visible)
    shadow: list[str]             # computed, invisible
    score: int
    band: Band
    engine_version: str = "rie-scorer v1"

def score_and_band(all_reasons: list[str]) -> Assessment:
    visible, shadow, pts, endo_pts = [], [], 0, 0
    for code in dict.fromkeys(all_reasons):           # dedupe, keep order
        meta, mode = R.get(code), MODE.get(code, SignalMode.SCORED)
        if meta is None:
            visible.append(code); continue
        if mode is SignalMode.SHADOW:
            shadow.append(code); continue
        visible.append(code)
        if mode is SignalMode.SCORED and not meta.hard:
            if meta.endogenous:
                endo_pts += meta.points               # capped: endogenous alone never reaches RED
            else:
                pts += meta.points
        if meta.hard and meta.category in (Category.FRAUD,):
            pts += 50                                 # hard fraud grounds band RED directly
    score = pts + min(endo_pts, ENDOGENOUS_POINT_CAP)
    band = Band.RED if score >= RED_AT else Band.AMBER if score >= AMBER_AT else Band.GREEN
    return Assessment(visible, shadow, score, band)

# ────────────────────────────────────────────────────────────────────────────
# 9. DISPOSITION — one shared worst-wins ordering                        (§9)
# ────────────────────────────────────────────────────────────────────────────

def disposition(assessment: Assessment, merits_pending: bool) -> Category:
    cats = {R[c].category for c in assessment.reasons if c in R}
    if merits_pending:
        cats.add(Category.MERITS)                     # held_for_merits
    for cat in Category:                              # enum order = precedence
        if cat in cats:
            return cat
    return Category.CLEAN

# ────────────────────────────────────────────────────────────────────────────
# 10. PAYMENT ELIGIBILITY — the last gate                               (§8e)
# ────────────────────────────────────────────────────────────────────────────

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
    return (not holds), round(max(payable - interim_paid, 0.0), 2), holds

# ────────────────────────────────────────────────────────────────────────────
# 11. THE PIPELINE — one claim, end to end
# ────────────────────────────────────────────────────────────────────────────

def process_claim(c: Claim, accidents: list[Accident], book: RefBook, rs: Ruleset,
                  today: date, provider_tier: str = "GP",
                  accident_dx_regions: set[str] = frozenset(),
                  seen_lines: set = None, cohort_is_bus_taxi: bool = False,
                  conv_floor_p10: float = 20.0, summons_served: Optional[date] = None) -> dict:
    """The brain, invoked once per claim. Deterministic. Returns the determination record."""
    seen_lines = seen_lines if seen_lines is not None else set()

    # A. anchor to the accident graph and refresh corroboration          (§6.0)
    accident, action = resolve_accident(c, accidents)
    accident.claims.append(c.claim_id)
    graph_reasons = corroboration_signals(accident, cohort_is_bus_taxi, conv_floor_p10)

    # B. grounded gates                                                   (§4)
    deceased_pre = bool(c.claimant_deceased_on and
                        any(l.service_date > c.claimant_deceased_on for l in c.lines))
    gate_reasons = (prescription_gates(c, rs, today, summons_served)
                    + s24_gates(c) + standing_gates(c, deceased_pre) + merits_gate(c))
    validated = not any(r in ("S24_INCOMPLETE", "OAR_MISSING") for r in gate_reasons)

    # C. per-line adjudication                                        (§3, §5f)
    line_results = [adjudicate_line(c, l, book, rs, provider_tier, seen_lines,
                                    set(accident_dx_regions)) for l in c.lines]
    line_reasons = [r for lr in line_results for r in lr.reasons]

    # D. heads (medical here; earnings/GD computed when their inputs arrive) (§5)
    medical_payable = head_past_medical(line_results, c.fault_pct)

    # E. score, band, disposition                                    (§10, §9)
    assessment = score_and_band(gate_reasons + line_reasons + graph_reasons)
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
        "engine_version": assessment.engine_version,
        "ruleset_effective": c.accident_date.isoformat(), "reference_edition": "RPL-2026",
    }
