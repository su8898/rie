# How the RIE Determines Risk

*A precise, self-contained description of how the RAF Integrity Engine turns one submitted claim into a risk verdict. Written from the engine itself (`engine/` — mirrored byte-for-byte by the oracle `spec/rie_engine.py`), not from intent. Every number and rule below is the one the code applies.*

> **Scope.** This is **claim-level** risk — one invoice, one determination. The other half of
> risk in RIE — the standing 0–100 score on an *actor* (provider / attorney / claimant),
> aggregated across everything they touch — is the companion:
> [how-party-risk-is-determined.md](how-party-risk-is-determined.md). Party risk is emergent
> from the determinations described here; it prioritises attention and never gates a payment.

---

## 1. The one idea to hold onto: risk is three independent answers, not one

When a claim is assessed, the engine does **not** produce a single "risk = 73%" figure. It produces **three separate verdicts on three orthogonal axes**, and conflating them is the most common way to misread the system:

| Axis | Question it answers | Values | Set by |
|---|---|---|---|
| **Band** | *How much does this claim have to answer for?* | `GREEN` / `AMBER` / `RED` | a **numeric score** from weighted signals |
| **Disposition** | *Where does this claim route?* | `FRAUD` / `MERITS` / `COMPLIANCE` / `PREAUTH` / `SI_GATE` / `ADJUSTED` / `CLEAN` | the **single worst signal category** (worst-wins) |
| **Eligibility** | *Can it be paid right now?* | eligible / held (+ a list of holds) | **gates and holds**, independent of score |

These move independently. A claim can be:

- **`GREEN` band but `FRAUD` disposition** — one low-weight fraud feature fired (routes to review) but the score never crossed a threshold.
- **`GREEN` band, `CLEAN`-ish, but *not* payable** — a hard compliance gate (e.g. a missing accident report) contributes **zero points** yet blocks payment outright.
- **`RED` band and held** — a high score *and* a gate.

The band is a **triage score**. The disposition is a **routing verdict**. Eligibility is a **payment gate**. The rest of this document explains exactly how each is computed and how they relate.

> **Determinism.** The whole assessment is a pure function of its inputs (`process_claim`). Same claim + same reference data + same rules ⇒ same determination, every time. The output record is stamped with the engine version and reference edition that produced it, so any determination is reproducible and auditable (provenance, §5/P5).

---

## 2. The unit of work: a *determination*

Every submitted claim is scored exactly once by `process_claim`, which returns a **determination record**:

```
claim_id, accident_id, accident_action, convergence,
validated, band, score, reasons[], shadow_signals[],
disposition, medical_payable, eligible_to_pay, net_payable, holds[],
engine_version, ruleset_effective, reference_edition
```

`band`, `disposition`, and `eligible_to_pay` are the three axes from §1. Everything else is either an input to them (`reasons`, `score`, `validated`, `convergence`) or a consequence (`medical_payable`, `net_payable`, `holds`).

---

## 3. Signals ("reasons") — the vocabulary of risk

Risk is expressed entirely through **reasons** (also called signals). A reason is a named rule that either fired or didn't, e.g. `OAR_MISSING`, `BILLED_OVER_REFERENCE`, `DX_ACCIDENT_MISMATCH`. **Nothing contributes to risk except through a reason** — there are no hidden weights.

### 3.1 Where reasons come from (the live pipeline)

`process_claim` gathers reasons from three families, then feeds them all into one scorer:

1. **Grounded gates (`engine/gates.py`, §4)** — statute-cited hard rules evaluated against the ruleset effective on the accident date:
   - *Prescription:* `PRESCRIBED_LODGEMENT` (lodged later than 3 years after the accident for an identified driver, 2 for hit-and-run, unless prescription is suspended), `PRESCRIBED_SUMMONS`.
   - *Documents (s24):* `OAR_MISSING` (no accident report — the universal mandatory item), `S24_INCOMPLETE` (any other mandatory document missing for the claim type).
   - *Standing:* `PROVIDER_UNREGISTERED`, `ATTORNEY_NOT_IN_STANDING`, `LIFE_STATUS_MISMATCH`.
   - *Merits:* if merits are explicitly rejected, the specific ground fires — `SOLE_NEGLIGENCE`, `S19_EXCLUSION`, or `NO_MVA_NEXUS`.
2. **Per-line adjudication (`engine/adjudication.py`, §3/§5f)** — evaluated for every billing line:
   - Hard causation/date gates: `SERVICE_BEFORE_ACCIDENT`, `DUPLICATE_LINE` (pay-once across claim types).
   - Undertaking / pre-authorisation: `UNDERTAKING_NOT_ACTIVE`, `UNDERTAKING_SCOPE`, `PREAUTH_MISSING`, `PREAUTH_EXCEEDED`.
   - Reference pricing: `DX_ACCIDENT_MISMATCH` (diagnosis doesn't corroborate the accident's injury regions), `BILLED_OVER_REFERENCE` (billed above the reference rate).
3. **Accident-graph corroboration (`engine/corroboration.py`, §6.0)** — computed once the claim is anchored to its accident: `CLAIMANT_SURGE` (more claimants than the accident report's occupants — a **low-confidence** input, since the occupant count is OAR-sourced; cohort-aware, so bus/taxi accidents are exempt; never a sole ground) and `CONVERGENCE_THIN` (too little independent evidence — see §7).

Two adjudication nuances that live in family 2: **emergency lines** (per the regulations' definition) are exempt from pre-authorisation and carry a leniency margin on utilisation-type signals — they are authorised retrospectively; and **`UNDERTAKING_SCOPE` has dual behaviour** — on an undertaking whose scope is ICD-coded it is a hard out-of-scope reject, but on a legacy free-text (uncoded) scope it fires soft and routes to medical review, where the reviewer codes the scope for next time (the scope-capture worklist).

**Register entries without a live emission point in this per-invoice pass.** One fires **later**, at head computation / offer assembly (a subsequent invocation of the same scorer): `GENERAL_DAMAGES_NO_SI`, emitted by the general-damages head when serious injury isn't accepted (§5d). Three more are **defined but emitted by no path today** — the accident graph and s17(5) make the checks *buildable*, but no detector fires them yet: `DUPLICATE_CLAIM` (a claim-level duplicate — same claimant, same accident, lodged twice, including cross-office — distinct from the per-line `DUPLICATE_LINE`), `SUPPLIER_PRECLUSION` (whose s17(5) pay-once role is served today by `DUPLICATE_LINE`), and `EARNINGS_UNPROVEN` (the loss-of-earnings proof gate). Each scores and routes exactly as registered the day its detector lands.

### 3.2 The reason register — one place that fixes every signal's meaning

Every reason is declared once, with fixed attributes, in the **reason register** (`engine/reasons.py`, the `R` table). This is the single source of truth for what a signal *means* for risk:

| Attribute | What it controls |
|---|---|
| **category** | the disposition lane the signal routes to (§5) — `FRAUD`, `MERITS`, `COMPLIANCE`, `PREAUTH`, `SI_GATE`, `ADJUSTED`, `CLEAN` |
| **hard** | `hard=True` is a **gate** (0 points, but repudiates/blocks on its own); `hard=False` is a **soft feature** that contributes points |
| **points** | the score weight a soft feature adds **when it is SCORED** (see §4) |
| **maturity** | the evidentiary grade — `GROUNDED` (law-cited), `HEURISTIC` (measured feature), `UNVALIDATED` (not yet calibrated) |
| **endogenous** | if `True`, the signal is derived from the corpus's own empirical distributions and counts toward a special cap (§6.2) |
| **basis** | the citation or method behind it — the defensibility note |

Because weight, category, maturity, and mode are **register data, not logic**, changing how much a signal counts (or whether it counts at all) is a reference-data edit, never a code change. The full register is in the Appendix.

> **A note on breadth.** The register catalogues more signals than the live per-claim pipeline currently emits — behavioural and party-graph detectors (`MATERIAL_PADDING`, `VALUE_OUTLIER`, `IMPOSSIBLE_DAY`, `RING_PARTIES`, `CLAIMANT_RECURRENCE`, …) are **defined with calibrated weights and launched in `SHADOW`** (§4.1) so that promoting a detector from invisible to scoring is a governed reference-data change, not a scoring rewrite. Wherever a detector supplies one of these reasons, it scores exactly as its register entry says.

---

## 4. Signal modes — whether a reason counts *today*

Maturity is the *evidentiary* grade of a signal; **mode** is its *operational* status — whether it is allowed to affect the score right now. There are three modes (`engine/vocab.py`):

| Mode | Visible to handlers? | Contributes points? | Meaning |
|---|---|---|---|
| **SHADOW** | no | no | computed and stored, but silent — a signal being watched before it is trusted |
| **ADVISORY** | yes | no | shown on the claim, but does not move the score |
| **SCORED** | yes | yes | fully live — adds its `points` to the band score |

### 4.1 The default mode and the promotion lifecycle (§11)

At launch, each reason's default mode is derived from its maturity (`MODE` in `engine/reasons.py`):

```
default mode = SHADOW  if maturity is UNVALIDATED
             = SCORED  otherwise   (GROUNDED and HEURISTIC signals score by default)
```

So the four `UNVALIDATED` graph/collusion signals (`RING_PARTIES`, `CLAIMANT_SURGE`, `CLAIMANT_RECURRENCE`, `CONVERGENCE_THIN`) start **silent**, while law-cited gates and measured heuristics score from day one.

A signal earns its way up the ladder **SHADOW → ADVISORY → SCORED** only on **measured precision**: the governance layer labels closed cases as ground truth, computes each signal's substantiation rate with a Wilson confidence interval, and a signal may be promoted to `SCORED` only when its **Wilson-lower bound ≥ 60%**. A `SCORED` signal that later drops below the floor is flagged for demotion. This is why weight is *earned*, not asserted.

### 4.2 Overriding a mode (ADMIN, audit-logged)

An operator can override a signal's mode (Admin → Signal modes). Overrides are **effective-dated, audit-logged reference data — never a code deploy**. One rule is inviolable: **`GROUNDED` (law-cited) signals are locked `SCORED` and cannot be overridden** — you cannot switch off the law. The override map is passed into the scorer as `mode_overrides` and takes precedence over the default.

---

## 5. Axis 1 — the risk **band** (`score_and_band`)

The band is a numeric triage score bucketed into three levels. Here is the **exact algorithm** (`engine/scoring.py`), in the order the code runs:

```
points        = 0     # normal soft-feature points
endo_points   = 0     # endogenous soft-feature points (capped separately)

for each distinct reason (de-duplicated, original order):
    meta = register[reason]                       # None if the code is unknown
    mode = override[reason]  or  default_mode[reason]  or  SCORED

    if meta is None:            keep it visible, contribute nothing
    if mode == SHADOW:          move to shadow_signals[], contribute nothing, hidden
    otherwise:                  keep it visible

    if mode == SCORED and not meta.hard:          # only SCORED soft features add points
        if meta.endogenous:  endo_points += meta.points
        else:                points      += meta.points

    if meta.hard and meta.category == FRAUD:      # a hard *fraud* ground lands RED directly
        points += 50

score = points + min(endo_points, 45)             # ENDOGENOUS_POINT_CAP = 45

band  = RED    if score >= 50                      # RED_AT   = 50
        AMBER  if score >= 25                      # AMBER_AT = 25
        GREEN  otherwise
```

### 5.1 The thresholds

| Band | Score range | Reading |
|---|---|---|
| **GREEN** | `0 – 24` | auto-clears on risk; the clean lane that carries the book |
| **AMBER** | `25 – 49` | needs a look |
| **RED** | `50 +` | worked first |

### 5.2 The five rules that fall out of that algorithm

1. **Only `SCORED` soft features add points.** Hard gates contribute **0 points** (they route and block via other axes — §5.3, §6). `SHADOW` signals contribute 0 and are hidden. `ADVISORY` signals are visible but contribute 0.
2. **Hard gates do not raise the band by themselves.** A claim can be entirely blocked by a hard compliance gate and still be **`GREEN`**, because the gate carries 0 points. Band ≠ blocked.
3. **A hard *fraud* ground lands `RED` immediately** (`+50`). *(The register currently defines no hard-fraud reason, so in practice `RED` is reached by soft fraud features summing to ≥ 50; the mechanism is reserved for a future law-cited fraud finding.)*
4. **Endogenous signals alone can never reach `RED`.** All endogenous points are summed and then **capped at 45** before being added — one point short of `RED`. A claim flagged only by corpus-derived outliers (`VALUE_OUTLIER`, `LINE_COUNT_OUTLIER`, `EARNINGS_OUTLIER`, …) tops out at `AMBER`; reaching `RED` requires at least one non-endogenous, externally-grounded signal. This is a deliberate false-positive guard: the system won't call something fraud on the strength of "it's unusual" alone.
5. **De-duplication.** The same reason firing twice counts once.

### 5.3 Worked band examples

| Signals that fired (all SCORED unless noted) | Point maths | Score | Band |
|---|---|---|---|
| none | — | 0 | **GREEN** |
| `OAR_MISSING` (hard, COMPLIANCE) | 0 (gate) | 0 | **GREEN** — *but blocked, see §6* |
| `DX_ACCIDENT_MISMATCH` (15) | 15 | 15 | **GREEN** — *fraud disposition though, see §5* below |
| `IMPOSSIBLE_DAY` (25) | 25 | 25 | **AMBER** |
| `IMPOSSIBLE_DAY` (25) + `DX_ACCIDENT_MISMATCH` (15) + `MATERIAL_PADDING` (15) | 55 | 55 | **RED** |
| `VALUE_OUTLIER_EXTREME` (30, endo) + `VALUE_OUTLIER` (15, endo) + `LINE_COUNT_OUTLIER` (15, endo) | `min(60, 45)` | 45 | **AMBER** — *endogenous cap; never RED* |
| `RING_PARTIES` (25) while in **SHADOW** | 0 (shadow) | 0 | **GREEN** — *silent until promoted* |

---

## 6. Axis 2 — the **disposition** (worst-wins routing)

The disposition decides which queue a claim lands in. It is **not** derived from the score — it is the **single worst category among the visible reasons** (`engine/disposition.py`, §9).

```
categories = { register[r].category for each visible reason r }
if merits are pending (a PERSONAL claim with merits neither accepted nor rejected):
    add MERITS
return the worst category present, in this fixed precedence:
```

### 6.1 The precedence order (worst first)

```
FRAUD  >  MERITS  >  COMPLIANCE  >  PREAUTH  >  SI_GATE  >  ADJUSTED  >  CLEAN
```

The claim is counted **once**, in its **worst** lane. If any fraud-category signal is visible, the claim is `FRAUD`, regardless of how many benign signals are also present. If nothing fired (and merits aren't pending), the disposition is `CLEAN`.

- `FRAUD` / `MERITS` / `COMPLIANCE` / `PREAUTH` / `SI_GATE` → **needs a human**.
- `ADJUSTED` → auto-processed with a repricing (e.g. billed over reference → paid at reference).
- `CLEAN` → auto-processed as billed.

Note that a **SHADOW** fraud signal does **not** set the disposition — only *visible* reasons count, and shadow signals are hidden. This is why a signal in shadow neither scores nor routes.

---

## 7. Convergence — is the accident even real? (`engine/corroboration.py`, §6.0)

Convergence is a separate, accident-level measure that sits behind the `CONVERGENCE_THIN` signal. A genuine accident leaves **independent traces that agree without coordinating** (police, ambulance, hospital, pharmacy, employer, independent claimants). Convergence scores how much independent corroboration exists, **0–100**:

```
convergence = 100 * (sum of the weights of the distinct source classes present) / 12.0
```

with independence weights:

| Source class | Weight | | Source class | Weight |
|---|---|---|---|---|
| SAPS (police) | 0.5 | | INDEPENDENT_CLAIMANT | 2.0 |
| EMS (ambulance) | 2.0 | | PHARMACY | 1.0 |
| HOSPITAL | 2.0 | | EMPLOYER | 1.0 |
| PREAUTH_L3 | 2.0 | | INJURY_COHERENCE | 1.5 |

*(`MAX_CONVERGENCE = 12.0`, the sum of all eight weights.)*

The crucial move: **sources that share one party-cluster** (the same attorney/provider network) **collapse to a single vote**. Ten documents produced by one colluding network count once, not ten — you cannot manufacture convergence by generating more paperwork from the same hand. If convergence falls below a calibrated floor (default `20.0`, taken from the genuine-accident band), `CONVERGENCE_THIN` fires. Convergence is *both-tailed* by this one mechanism: a thin evidence trail scores low directly, and a suspiciously **dense but single-cluster** trail *also* scores low — the collapse reduces its many documents to one vote — so manufactured density fires the same `CONVERGENCE_THIN` flag as thinness. Density only raises convergence when it comes from hands that don't know each other.

---

## 8. Axis 3 — payment **eligibility** (`engine/payments.py`, §8e)

Eligibility is the last gate and is, again, **independent of the score**. A claim is payable only if **no hold** applies. Holds accumulate:

| Hold | Fires when |
|---|---|
| `held_<disposition>` | disposition is anything other than `CLEAN` or `ADJUSTED` (e.g. `held_fraud`, `held_compliance`) |
| `held_for_validation` | a hard document gate is unmet (`S24_INCOMPLETE` or `OAR_MISSING`) — i.e. `validated = False` |
| `held_for_merits` | a `PERSONAL` claim whose merits are not yet accepted |
| `PAYEE_UNVERIFIED` | the payee failed account verification (AVS) |
| `ATTORNEY_NOT_IN_STANDING` | the attorney is not in good standing (payment hold) |
| `LIFE_STATUS_MISMATCH` | the claimant is recorded deceased |

```
eligible_to_pay = (no holds)
net_payable     = max(payable − interim_already_paid, 0)     # nets off any interim payment, s17(6)
```

Only `CLEAN` and `ADJUSTED` claims can pay without human sign-off; every other disposition creates a `held_*` and must be worked. This is the mechanism behind "`GREEN` but not payable": a zero-point hard gate produces a hold.

---

## 9. Putting it together — one claim, end to end (`process_claim`)

```
A. Anchor the claim to the accident graph: normalised case number (exact) else a
   fuzzy date/place/vehicle/party score — auto-join ≥ 0.85, human match-worklist ≥ 0.50,
   else a new accident record; compute convergence + corroboration signals.        → CONVERGENCE_THIN, CLAIMANT_SURGE
B. Run the grounded gates against the ruleset effective on the accident date.       → gate reasons; sets `validated`
C. Adjudicate every line: causation/date gates, undertaking/pre-auth, then price
   payable = min(billed, reference) on ENFORCEABLE/ACCEPTED sources (signal-only
   on INTERDICTED/ENDOGENOUS).                                                       → line reasons; per-line payable
D. Sum the medical head (apportioned by (1 − fault%)).                              → medical_payable
E. SCORE + BAND  = score_and_band(gate + line + graph reasons, overrides).          → band, score, reasons, shadow_signals
   DISPOSITION   = worst-wins over the visible reasons (+ MERITS if pending).       → disposition
F. ELIGIBILITY   = eligible_to_pay(...).                                            → eligible_to_pay, net_payable, holds
→ return the provenance-stamped determination record.
```

The reference-pricing rule in step C is the money rule that underlies the whole payment path: **`payable = min(billed, reference)`**. A line billed above an *enforceable or accepted* reference is **repriced** (paid at reference, the difference captured), not rejected; a line billed above a *signal-only* source (interdicted tariff / empirical median) is flagged for review but not auto-cut.

---

## 10. Four end-to-end illustrations

**(1) A clean supplier invoice.** All mandatory documents present; each line at or under its RPL rate; diagnosis corroborates the accident. No reasons fire. **Score 0 → GREEN. Disposition CLEAN. Eligible.** Pays as billed.

**(2) Over-billed but honest.** One line billed above its enforceable RPL rate. `BILLED_OVER_REFERENCE` fires — an `ADJUSTED`, **soft, 0-point, GROUNDED** signal. **Score 0 → GREEN**, but **disposition `ADJUSTED`** (worst-wins), and the line is **repriced to the reference**. Still eligible (`ADJUSTED` pays); `net_payable` reflects the reprice, not the bill.

**(3) A single diagnosis mismatch.** The billed diagnosis region doesn't match the accident profile. `DX_ACCIDENT_MISMATCH` fires (`FRAUD`, soft, **15 pts**). **Score 15 → GREEN band**, but **disposition `FRAUD`** → it routes to human review and is **held** (`held_fraud`). This is the canonical *band ≠ disposition ≠ eligibility* case: low score, fraud lane, not payable.

**(4) A missing accident report.** `OAR_MISSING` fires (hard `COMPLIANCE`, **0 pts**). **Score 0 → GREEN**, `validated = False`, **disposition `COMPLIANCE`**, and **not eligible** (`held_compliance` + `held_for_validation`). A "green" risk score that is nonetheless completely blocked — because eligibility is a gate, not a score.

---

## 11. Why it is built this way (design guarantees)

- **Separation of triage, routing, and payment.** Three axes mean a cheap gate (a missing form) never inflates a fraud score, and a genuine fraud score never silently authorises payment. Each control does one job.
- **Every point is defensible.** No signal contributes without a register entry carrying a maturity grade and a citation/method (`basis`). Nothing is a black box.
- **Weight is earned, not asserted.** A signal only scores once its measured precision clears the Wilson-lower ≥ 60% floor; unproven signals run silently in `SHADOW` first. Law-cited signals are exempt (always `SCORED`) and cannot be switched off.
- **False-positive guards are structural.** Endogenous ("it's unusual here") signals are capped below `RED`; corroboration collapses same-network sources to one vote; cohort-relative comparisons stop a legitimate specialty from looking anomalous.
- **Tuning is data, not code.** Signal weights, modes, statutory caps, pre-auth sets, and negotiated rates are all reference/config data (edited in Admin, audit-logged, effective-dated). Re-tuning risk never requires a deploy.
- **Reproducible.** The determination is a deterministic function stamped with its engine version and reference edition — any verdict can be replayed and audited.

---

## Appendix — the complete reason register

Every signal the system can express, with its fixed attributes (`engine/reasons.py`). **Points apply only when the signal is `SCORED` and soft;** hard gates always carry 0 points. Default mode is `SHADOW` for `UNVALIDATED` signals, `SCORED` otherwise.

### Hard gates (all `GROUNDED`, 0 points — they route and block, they do not score)

| Reason | Category | Basis |
|---|---|---|
| `PRESCRIBED_LODGEMENT` | COMPLIANCE | s23 |
| `PRESCRIBED_SUMMONS` | COMPLIANCE | s23(3) |
| `S24_INCOMPLETE` | COMPLIANCE | s24 |
| `OAR_MISSING` | COMPLIANCE | s24 + reg |
| `DUPLICATE_CLAIM` | COMPLIANCE | one claim per claimant per accident |
| `PROVIDER_UNREGISTERED` | COMPLIANCE | HPCSA/BHF register |
| `ATTORNEY_NOT_IN_STANDING` | COMPLIANCE | LPC register (payment hold) |
| `PAYEE_UNVERIFIED` | COMPLIANCE | AVS |
| `LIFE_STATUS_MISMATCH` | COMPLIANCE | DHA / death certificate (§5g) |
| `SOLE_NEGLIGENCE` | MERITS | s17(1) |
| `S19_EXCLUSION` | MERITS | s19 |
| `NO_MVA_NEXUS` | MERITS | s17(1) driving nexus |
| `SERVICE_BEFORE_ACCIDENT` | COMPLIANCE | date check |
| `SUPPLIER_PRECLUSION` | ADJUSTED | s17(5) — pay once |
| `DUPLICATE_LINE` | ADJUSTED | pay first occurrence |
| `PREAUTH_MISSING` | PREAUTH | §5f ruleset |
| `PREAUTH_EXCEEDED` | ADJUSTED | §5f — reprice to ceiling |
| `UNDERTAKING_NOT_ACTIVE` | COMPLIANCE | s17(4)(a) |
| `UNDERTAKING_SCOPE` | COMPLIANCE | undertaking terms — hard on a coded scope; fires **soft → review** on legacy uncoded scopes (§3.1) |
| `GENERAL_DAMAGES_NO_SI` | SI_GATE | reg 3 / RAF 4 |
| `EARNINGS_UNPROVEN` | COMPLIANCE | proof requirement |

### Soft features (contribute `points` when `SCORED`)

| Reason | Category | Points | Maturity | Endogenous | Basis |
|---|---|---|---|---|---|
| `BILLED_OVER_REFERENCE` | ADJUSTED | 0 | GROUNDED | — | repriced when enforceable/accepted; else signal |
| `PRE_EXISTING_CONDITION` | COMPLIANCE | 5 | HEURISTIC | — | review — aggravation compensable |
| `OAR_MISMATCH` | FRAUD | 5 | HEURISTIC | — | SAPS data quality (LOW, never sole ground) |
| `EARNINGS_OUTLIER` | FRAUD | 10 | HEURISTIC | ✓ | sector band |
| `VALUE_OUTLIER` | FRAUD | 15 | HEURISTIC | ✓ | condition band p90 |
| `LINE_COUNT_OUTLIER` | FRAUD | 15 | HEURISTIC | ✓ | corpus percentile |
| `MATERIAL_PADDING` | FRAUD | 15 | HEURISTIC | — | NAPPI-dominated encounter |
| `DX_ACCIDENT_MISMATCH` | FRAUD | 15 | HEURISTIC | — | body region vs accident profile |
| `INJURY_ESCALATION` | FRAUD | 15 | HEURISTIC | — | RAF1/4 vs first-contact records |
| `OAR_REUSED` | FRAUD | 15 | HEURISTIC | — | conflicting accident records, one CAS |
| `LATE_CLAIM_CLUSTER` | FRAUD | 15 | HEURISTIC | — | deadline clustering |
| `IMPOSSIBLE_DAY` | FRAUD | 25 | HEURISTIC | — | billed minutes > plausible day |
| `VALUE_OUTLIER_EXTREME` | FRAUD | 30 | HEURISTIC | ✓ | condition band, extreme |

### Graph / collusion signals (launch in `SHADOW`; `UNVALIDATED`)

| Reason | Category | Points | Basis |
|---|---|---|---|
| `CLAIMANT_RECURRENCE` | FRAUD | 15 | P_* token across accidents |
| `CLAIMANT_SURGE` | FRAUD | 20 | claimants vs capacity, cohort-aware |
| `CONVERGENCE_THIN` | FRAUD | 20 | evidence density/timing (§6.0) |
| `RING_PARTIES` | FRAUD | 25 | party-graph recurrence |

**Designed, not yet in the register** (domain-logic §10): `TOUT_PATTERN`, `WPI_INFLATION`, `EXPERT_MILL`, `ATTORNEY_CONCENTRATION` — their detectors need data feeds (and, for the first two, the medico-legal-expert party type) that aren't live. Per the promotion doctrine, each enters the register **in `SHADOW`** when its detector lands — never directly at `SCORED`.

### Constants

| Constant | Value | Meaning |
|---|---|---|
| `AMBER_AT` | 25 | score at/above which a claim is at least `AMBER` |
| `RED_AT` | 50 | score at/above which a claim is `RED` |
| `ENDOGENOUS_POINT_CAP` | 45 | ceiling on total endogenous points (one short of `RED`) |
| `MAX_CONVERGENCE` | 12.0 | sum of source-class weights (convergence denominator) |
| convergence floor | 20.0 | below which `CONVERGENCE_THIN` fires (default) |
| accident auto-join | ≥ 0.85 | fuzzy match score at which a claim joins an accident without a human |
| accident match-worklist | ≥ 0.50 | fuzzy match score routed to a human to confirm/create |
| promotion floor | Wilson-lower ≥ 60% | measured-precision bar to promote a signal to `SCORED` |
| prescription | 3 yr identified / 2 yr hit-and-run | lodgement window (`PRESCRIBED_LODGEMENT`) |

---

*Source of truth: `engine/` (`scoring.py`, `reasons.py`, `vocab.py`, `disposition.py`, `gates.py`, `adjudication.py`, `corroboration.py`, `payments.py`, `pipeline.py`), mirrored byte-for-byte by `spec/rie_engine.py`. Section markers (§) refer to `domain-logic.md`. If this document and the engine ever disagree, the engine is correct — regenerate this from it.*
