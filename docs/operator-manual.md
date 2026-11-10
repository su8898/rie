# RIE Operator Manual

*How to operate the RAF Integrity Engine, by role. This is the practical, task-oriented companion to the two risk specifications — [how-risk-is-determined.md](how-risk-is-determined.md) (claim-level) and [how-party-risk-is-determined.md](how-party-risk-is-determined.md) (party-level). Where those explain *how the engine decides*, this explains *what each operator does*. Role capabilities below are taken from the code — the endpoint role guards, the state-machine actor roles, and the workflow permission map — so they match what the system will actually let you do.*

---

## Contents

1. [Introduction](#1-introduction)
2. [Signing in & the five roles](#2-signing-in--the-five-roles)
3. [Concepts every operator needs](#3-concepts-every-operator-needs)
4. [Who can do what — the capability matrix](#4-who-can-do-what--the-capability-matrix)
5. [Role guide: Handler](#5-role-guide-handler)
6. [Role guide: Medical Officer](#6-role-guide-medical-officer)
7. [Role guide: Investigator](#7-role-guide-investigator)
8. [Role guide: Legal](#8-role-guide-legal)
9. [Role guide: Admin](#9-role-guide-admin)
10. [The claim's journey — how the roles hand off](#10-the-claims-journey--how-the-roles-hand-off)
11. [Page reference](#11-page-reference)
12. [Troubleshooting](#12-troubleshooting)
13. [Glossary](#13-glossary)

---

## 1. Introduction

RIE is a claims-integrity platform for Road Accident Fund medical claims. An operator's job is to move claims safely from **intake** to **payment**, catching what shouldn't be paid and paying what should — accurately, defensibly, and with a clean audit trail.

The engine does the scoring; **you make the decisions.** Every claim is scored automatically the moment it is submitted (band, disposition, eligibility — see §3), but a scored claim is not a paid claim: humans validate merits, assemble and approve payments, investigate fraud, and handle disputes and litigation. This manual is your map to those tasks.

**Two principles run through everything:**

- **The backend is authoritative.** Buttons you cannot use are greyed out as a courtesy, but the real enforcement is server-side. If you try something your role can't do, you get a clear refusal (`forbidden for role …`) rather than a silent failure. The UI never lets you *think* you did something you didn't.
- **Every change is logged.** Configuration edits, payment approvals, case verdicts, dispute outcomes — all are recorded with who, what, and when. Nothing mutates silently.

---

## 2. Signing in & the five roles

Sign in at the login screen with your username and password. In a demo build, the **dev logins** panel gives one-click sign-in for each role (username = password): `admin`, `handler`, `medical`, `investigator`, `legal`.

Your **role** determines which navigation items and actions are available. There are five:

| Role | In one line | Think of them as… |
|---|---|---|
| **HANDLER** | assesses and adjudicates claims end to end | the claims caseworker |
| **MEDICAL_OFFICER** | the clinical authority — serious-injury and undertakings | the medical reviewer |
| **INVESTIGATOR** | fraud investigation and post-payment recovery | the enforcement arm |
| **LEGAL** | disputes, referrals, and litigation | the legal team |
| **ADMIN** | runs the console, holds the money keys, superuser | the administrator |

> **ADMIN is a superuser.** Anywhere this manual says a task needs role X, an ADMIN can also do it — the role check is bypassed for ADMIN. This is deliberate but powerful: ADMIN can both configure the system *and* move money, so ADMIN accounts are the ones to guard most closely (and segregation of duties, §3, still applies to *who* approves *what*).

---

## 3. Concepts every operator needs

A short shared vocabulary. The risk specs cover the mechanics; here is what you need to *operate*.

**The three axes of a determination.** Every claim carries three independent verdicts — don't conflate them (full detail in [how-risk-is-determined.md](how-risk-is-determined.md)):

- **Band** — `GREEN` / `AMBER` / `RED` — a triage score. How much scrutiny the claim earns.
- **Disposition** — `FRAUD` / `MERITS` / `COMPLIANCE` / `PREAUTH` / `SI_GATE` / `ADJUSTED` / `CLEAN` — where it routes (worst-wins).
- **Eligibility** — payable now, or **held** (with a list of holds). A gate, not a score.

The consequence you'll meet daily: a claim can be **`GREEN` but held** (a missing document blocks it though the risk score is zero), or **`GREEN` but `FRAUD`-routed** (a single low-weight fraud feature sends it to review). Read all three.

**Holds.** A claim that isn't payable lists *why*: `held_for_validation` (a document gate), `held_for_merits` (merits not accepted), `held_fraud`/`held_compliance`/… (its disposition), `PAYEE_UNVERIFIED`, `ATTORNEY_NOT_IN_STANDING`, `LIFE_STATUS_MISMATCH`. Clearing a hold is the work.

**The claim lifecycle.** Beyond the instant determination, a claim moves through a state machine you drive on its detail page: `LODGED → VALIDATED → MERITS → QUANTUM → OFFER_MADE → SETTLED` (or `→ LITIGATION`) `→ PAID → FINALIZED`. Different states unlock different actions for different roles (§10).

**Segregation of duties.** On payments, the operator who **assembles** a batch must not be the one who **approves** it, and both are distinct from configuration. This is enforced — it's the control that stops one person paying themselves.

**Reading the screen.** Coloured chips encode state at a glance: band chips (green/amber/rose), disposition chips, state chips on every workflow entity, maturity/mode chips on signals. A greyed button with a tooltip (`Requires role: …`) means your role can't fire that transition *right now*; the transition may also simply not be legal from the current state.

---

## 4. Who can do what — the capability matrix

`✓` = allowed. **ADMIN can do everything** (superuser), so ADMIN is only marked where it is the *primary* or *sole* authority. "any" = any signed-in operator.

| Task | HANDLER | MEDICAL_OFFICER | INVESTIGATOR | LEGAL | ADMIN |
|---|:--:|:--:|:--:|:--:|:--:|
| **Read** dashboards, claims, intelligence, reference, reasons | any | any | any | any | any |
| **Submit / assess** a claim | ✓ | ✓ | | | ✓ |
| Lifecycle: **validate**, reject-compliance, open-merits, make-offer | ✓ | | | | ✓ |
| Lifecycle: **accept-merits**, repudiate, settle | ✓ | | | ✓ | ✓ |
| Lifecycle: **litigate**, court-order | | | | ✓ | ✓ |
| Lifecycle: **pay** | | | | | ✓ (sole) |
| Lifecycle: **finalize** | ✓ | | | | ✓ |
| **Build the offer** (the six heads) | ✓ | | | | ✓ |
| **Merits** accept / reject | ✓ | | | ✓ | ✓ |
| **Merits** appeal / dismiss | | | | ✓ | ✓ |
| **Serious injury (RAF 4)** create / accept / reject | | ✓ | | | ✓ |
| **Serious injury** appeal / uphold / dismiss | | | | ✓ | ✓ |
| **Undertakings** create / activate | ✓ | ✓ | | | ✓ |
| **Undertakings** suspend / resume | | ✓ | ✓ | | ✓ |
| **Undertakings** terminate / lapse | | ✓ (term.) | | | ✓ |
| **Undertaking invoices** submit / adjudicate / approve / reject | | ✓ | | | ✓ |
| **Undertaking invoices** pay | | | | | ✓ (sole) |
| **Litigation** open / plead / trial / judgment / settle | | | | ✓ | ✓ |
| **Litigation** order-paid | | | | | ✓ (sole) |
| **Cases** — open a case | any | any | any | any | any |
| **Cases** — REVIEW lane assign / escalate / close | ✓ | | | | ✓ |
| **Cases** — BLOCK / CLAWBACK lane; close escalated | | | ✓ | | ✓ |
| **Disputes** — lodge / withdraw | any | any | any | any | any |
| **Disputes** — reconsider / uphold / reject | ✓ | ✓ | | ✓ | ✓ |
| **Disputes** — refer / resolve (HPCSA / litigation) | | | | ✓ | ✓ |
| **Payments** — new batch / add instruction / cancel | ✓ | | | | ✓ |
| **Payments** — approve | | | | | ✓ (≠ assembler) |
| **Payments** — pay | | | | | ✓ (sole) |
| **Audit** — recovery sweep / review / recover / clear | | | ✓ | | ✓ |
| **Governance** — view precision / recall / labels | any | any | any | any | any |
| **Governance** — draw QA reviews into Cases | any | any | any | any | any |
| **Governance** — apply a signal-mode promotion | | | | | ✓ (sole) |
| **Admin** — users, caps, negotiated, pre-auth, signal modes | | | | | ✓ (sole) |

---

## 5. Role guide: Handler

**You are the claims caseworker** — the workhorse of the Fund. You take a claim from submission through validation, merits, offer, and settlement, and you assemble the batches that pay it.

**Your pages:** Submit · Claims → Claim detail (Workflow panel) · Cases (REVIEW lane) · Payments · Disputes · plus all the read-only analytics.

### 5.1 Submit and read a claim

1. Go to **Submit**. Fill the claim: id, type (`PERSONAL` / `SUPPLIER` / `UNDERTAKING_INVOICE`), party token, accident and lodgement dates, the case number (the OAR), the documents, and the billing lines (tariff/NAPPI code, amount, service date, diagnosis).
2. Watch the **payload preview** update live — it's exactly what the engine reads.
3. **Submit claim.** The engine scores it and you land on the determination.
4. On **Claims**, filter by band/disposition or search by claim/accident id; click any row to open its **detail**.

### 5.2 Drive the lifecycle (Claim detail → Workflow)

The claim-detail page has a **Workflow** panel with one sub-panel per state machine. You act mostly in **Lifecycle**, **Merits**, and **Offer**:

- **Validate** the claim (Lifecycle) once its documents/gates are satisfied. If it fails compliance, **reject-compliance**.
- **Open merits**, then in the **Merits** panel **accept** (entering the fault %) or **reject** (choosing the ground — `S19_EXCLUSION` / `SOLE_NEGLIGENCE` / `NO_MVA_NEXUS`). Fault % apportions every head.
- **Build the offer** (Offer panel): tick the heads that apply — loss of earnings, loss of support, general damages (a manual band, or computed from the comparable-awards store by injury class), funeral — and **Build offer**. The offer shows its total, per-head breakdown, and anything it's **gated by** (e.g. general damages gated until serious injury is accepted).
- **make-offer → settle** to conclude (you or Legal), or hand to Legal if it repudiates.
- **Finalize** once paid.

### 5.3 Work a REVIEW case

When a claim is flagged for a look, open or pick it up in **Cases** (the REVIEW lane is yours):

1. **Open case** (or select an existing REVIEW case). Set lane `REVIEW`, a reason, priority (P1–P5 sets the SLA clock), and rand-at-stake.
2. **assign** it to yourself (one click), work it, then **close** with a verdict, root cause, and any recovered/prevented amounts. If it needs the fraud team, **escalate** — it moves to the Investigator pool.

Your verdict on close becomes a **ground-truth label** that tunes the engine (governance precision/recall). Judge the merits honestly.

### 5.4 Assemble a payment batch

In **Payments** (see §10 for the full flow): **New batch**, then add instructions from the **eligible queue** (claims that cleared the gate) — pick a claim, choose the source and amount, **Add**. You assemble; a **different ADMIN approves**, and ADMIN pays. You cannot approve or pay your own batch — that's the segregation-of-duties control.

---

## 6. Role guide: Medical Officer

**You are the clinical authority.** Two things are yours alone: the **serious-injury (RAF 4)** gate that unlocks general damages, and the **undertakings** that pre-authorise future treatment (and their invoices). You can also submit and assess claims and take part in dispute reconsiderations.

**Your pages:** Submit · Claim detail (Workflow → Serious injury, Undertakings) · Disputes · analytics.

### 6.1 Serious injury (RAF 4)

General damages do not pay without an accepted serious-injury assessment — that's the `GENERAL_DAMAGES_NO_SI` gate. On a claim's **Workflow → Serious injury (RAF 4)** panel:

1. **Create RAF 4**: tick **list match** (a listed injury), enter **WPI %** (the whole-person-impairment score; ≥ 30% is the numeric threshold), and/or tick **narrative** (the narrative test).
2. **accept** or **reject** the assessment. Once accepted, the general-damages head can be offered. If rejected, Legal may **appeal** it to the HPCSA tribunal.

### 6.2 Undertakings and their invoices

An undertaking is the Fund's promise to pay defined future treatment. On the **Undertakings** panel:

1. **Issue** an undertaking: choose the origin (`SETTLEMENT` / `EMERGENCY`) and the scope diagnoses it covers.
2. **activate** it (you or a Handler). While `ACTIVE`, providers **submit invoices** against it — each is priced against its scope and reference.
3. **adjudicate** an invoice (entering the approved amount), then **approve** or **reject** it. ADMIN pays approved invoices.
4. If something looks wrong, **suspend** the undertaking (you or an Investigator); **resume** when cleared; **terminate** to end it.

### 6.3 Dispute reconsideration

You can take a lodged dispute **under reconsideration** and **uphold** or **reject** it (alongside Handler and Legal) — see §8 for the dispute flow. Referral to the HPCSA tribunal, though, is Legal's.

---

## 7. Role guide: Investigator

**You are the enforcement arm** — fraud investigation before payment, and recovery after it. You own the `BLOCK` and `CLAWBACK` case lanes and the post-payment **Audit** recovery process.

**Your pages:** Intelligence · Cases (BLOCK / CLAWBACK) · Audit · Accidents · analytics.

### 7.1 Find who to look at (Intelligence)

**Intelligence** scores parties, cohort-relative and n-guarded (see [how-party-risk-is-determined.md](how-party-risk-is-determined.md)):

- **Providers / Attorneys** — sortable, searchable tables of composite 0–100 scores with a rating and an expandable component breakdown. High scores are *shortlists*, not verdicts.
- **Claimants** — recurrence: a party token spanning ≥ 2 accidents (a possible ring).
- **Risk sweep** — one threshold across every provider and attorney, worst-first. Lower it to widen the net. **It only ranks** — acting on a flagged party means opening a case (next step).

### 7.2 Work a BLOCK / CLAWBACK case

In **Cases**, the `BLOCK` (stop a suspect claim) and `CLAWBACK` (recover a paid one) lanes are yours:

1. **Open case** on the flagged claim/party (lane `BLOCK` or `CLAWBACK`), or pick up an **escalated** case from the Handler pool.
2. **assign**, investigate, and **close** with a verdict — `CONFIRMED_FRAUD` / `CLEARED` / `ADJUSTED` / `NO_ACTION` / `REFERRED_LEGAL` — plus root cause and recovered/prevented amounts. Escalated cases are closed by you.

### 7.3 Post-payment recovery (Audit)

**Audit** is your clawback workflow. **Run recovery sweep** at a score floor to open clawback items on already-paid claims flagged RED/FRAUD or touched by a high-risk provider. Then per item: **review** to pick it up, **recover** (recording the amount returned and an outcome — `RECOVERED_FULL` / `PARTIAL` / `WRITTEN_OFF` / `NOT_PURSUED`) or **clear** if it isn't worth pursuing. The **recovery-rate** (recovered ÷ at-stake) is the realised ROI of the whole integrity effort.

### 7.4 Undertakings

You can **suspend** and **resume** an active undertaking when an investigation warrants it (with the Medical Officer).

---

## 8. Role guide: Legal

**You are the legal team** — the escalation path for anything contested. You refer disputes out, run litigation, and handle merits and serious-injury appeals.

**Your pages:** Disputes · Claim detail (Workflow → Merits, Serious injury, Litigation, Lifecycle) · analytics.

### 8.1 Disputes (the objection register)

**Disputes** is the s91-style objection register. Anyone can **lodge** an objection (subject: `MERITS` / `QUANTUM` / `TARIFF` / `REPUDIATION` / `SERIOUS_INJURY`; raised by claimant / provider / attorney). From there:

- Any of Handler / Medical Officer / Legal takes it **under reconsideration** and **upholds** or **rejects** it.
- **Referral is yours alone.** **refer** a dispute out: a `SERIOUS_INJURY` objection goes to the **HPCSA tribunal**; anything else opens a **litigation** record. After an external outcome, **resolve** it. (A raiser may **withdraw** at any open stage.)

### 8.2 Litigation

When a claim is repudiated or a dispute is litigated, drive the matter on the claim's **Workflow → Litigation** panel: **open litigation**, then **plead → set trial → judgment** (or **settle**), or **default judgment**. ADMIN records **order-paid**; you (or ADMIN) **close** the matter. In the **Lifecycle** panel you also drive **litigate**, **court-order**, and **settle**.

### 8.3 Merits and serious-injury appeals

- **Merits:** you can **accept**/**reject** (with a Handler) and, after a rejection, **appeal** it — then **accept** or **dismiss** the appeal.
- **Serious injury:** you **appeal** a rejected RAF 4 assessment and **uphold** or **dismiss** that appeal (the tribunal path).

---

## 9. Role guide: Admin

**You run the console and you hold the money keys.** Admin has two hats: the **configuration authority** (users, statutory config, reference tiers, signal modes) and the **payment authority** (approve and pay). Admin is also a superuser — so use it deliberately.

**Your pages:** Admin · Payments (approve/pay) · Governance (apply promotions) · everything else.

### 9.1 The Admin console

**Admin** has nine tabs; every change is audit-logged and effective-dated — it's reference data, never a code deploy:

- **Users** — create operators, set roles, activate/deactivate. (You cannot deactivate the account you're signed in as.)
- **Signal modes** — apply the `SHADOW → ADVISORY → SCORED` promotion lifecycle per signal. The *Recommended* column is what measured precision suggests (Governance computes the Wilson-lower ≥ 60% floor; you **Set** it here). `GROUNDED`, law-cited signals are locked `SCORED` — you cannot switch off the law.
- **Caps** — the s17(4)(c) statutory annual-cap schedule (effective-dated; the engine applies the cap effective on the service date).
- **Pre-auth** — the set of codes that require pre-authorisation (add/remove).
- **Negotiated** — negotiated ENFORCEABLE rates that override the gazetted tariff (the engine prices `min(billed, negotiated)` for these).
- **Dated rates** — the tariff, negotiated and NAPPI exit-price rates as dated versions. Add a rate from an effective date and the prior one is closed the day before; the engine pays each line at the rate in force on its **service date**, so late claims price at the tariff of their day. Also: percentage increase (one rate or every rate in the filter), correct, retire, CSV import/export, and the change log. A negotiated rate that has dated versions is maintained here, not on the Negotiated tab.
- **Coding rules** — the tariff's own billing rules per code. *Once per encounter*: a repeat for the same claimant, provider and day is not paid (`UNBUNDLING_CONFLICT`). *Time* rules: the billed quantity is minutes and the line is priced by its ladder off the block rate, not per minute. *Percentage of time*: a share of the anaesthetic-time lines billed with it; with none on the claim the line goes to review. The reference loader seeds the list from the tariff; a rule you set here is kept on reload. Check the seeded once-only codes against the gazette, because the descriptions were read by OCR.
- **Channel keys** — who may connect to the provider channel. Each connecting party (a provider's own system, or a switch) signs its requests with a private key only it holds; you register the matching **public** key here, with the provider ids the party may act for. A switch may be given `*` for any provider. **Suspend** refuses a party's signatures at once. Never accept or paste a private key: the form refuses one, and a party that sent one must generate a new pair.
- **Audit** — the append-only log of every admin mutation.

### 9.2 Approve and pay (the money keys)

**Medical reports.** A provider files the RAF 1 medical report and the RAF 4 serious injury assessment electronically. They appear on the claim's page under **Medical reports on file**, each with a **Print** page and an **XML** document. The two chips at the top show, per form, whether one is on file and whether a complete one is. A report marked *Incomplete* lists the required fields the provider left empty; ask the provider to file a corrected report. When a complete RAF 4 arrives for a personal claim with no serious-injury assessment, the assessment is opened for the Medical Officer automatically, carrying the form's impairment percentage and narrative finding.

When a batch is paid, the system issues a **remittance advice** for each provider paid in it, listed at the foot of **Payments**. Each advice shows every line billed, what was paid and why any line was reduced, and has a **Print** page and an **XML** document. Providers fetch and acknowledge their own advice over the rails channel, and the status changes to *Acknowledged* when they do. An advice never shows a review or fraud signal. A provider's objection to a reduction arrives in **Disputes** with *raised by PROVIDER*.

In **Payments**, you are the second and third pair of hands: **approve** a batch a Handler assembled (you must be a *different* admin than the assembler — segregation of duties), then **pay** it. You are the sole authority for `pay`, lifecycle `pay`, undertaking-invoice `pay`, and litigation `order-paid`.

### 9.3 Close the governance loop

In **Governance**, when a signal's measured precision clears the floor, **apply** the promotion in place (this calls the same signal-mode edit as the Admin tab, audit-logged). Use **Draw QA reviews** to seed blind review cases that keep the recall estimate honest.

---

## 10. The claim's journey — how the roles hand off

A single claim can pass through every role. Here is the end-to-end path and who does each step:

```
                    ┌─────────────────────────────────────────────────────────┐
   HANDLER /        │  1. INTAKE — submit the claim (Submit)                   │
   MEDICAL_OFFICER  │     → engine scores it: band + disposition + eligibility │
                    └─────────────────────────────────────────────────────────┘
                                              │
                          ┌───────────────────┴───────────────────┐
                 CLEAN / ADJUSTED, eligible              FLAGGED / held
                          │                                       │
                          │                              INVESTIGATOR (if fraud-routed)
                          │                              2b. Cases: BLOCK/CLAWBACK →
                          │                                  verdict labels the claim
                          ▼                                       │
   HANDLER    2. VALIDATE → open merits → accept merits (fault %) ◄┘
   MEDICAL    3. SERIOUS INJURY (RAF 4) if general damages are claimed
   HANDLER    4. BUILD OFFER — the six heads (gated by SI, merits, caps)
   HANDLER/   5. SETTLE  ─────────────or────────────►  LEGAL: repudiate → LITIGATION
   LEGAL                                                (pleadings → trial → judgment)
                          │                                       │
                          ▼                                       ▼
   HANDLER    6. PAYMENT — assemble a batch (Payments) ◄──── court order / settlement
   ADMIN         → a DIFFERENT admin APPROVES → ADMIN PAYS → lifecycle PAID
                          │
   INVESTIGATOR 7. POST-PAYMENT — recovery sweep (Audit) claws back on flagged paids
   HANDLER/     8. FINALIZE
   ADMIN
```

Alongside this, two flows run continuously:

- **Disputes** (any raiser → reconsideration by Handler/MO/Legal → Legal refers to HPCSA or litigation).
- **Governance** (ADMIN watches precision/recall, draws QA review cases, and applies signal-mode promotions as evidence accrues).

---

## 11. Page reference

| Page | What it's for | Primary users |
|---|---|---|
| **Dashboard** | the book at a glance — determination counts, band mix, disposition breakdown, money | all |
| **Claims** | the determination table — filter/search, open a claim's detail | all (Handler acts) |
| **Claim detail** | one claim's full record + the **Workflow** panel (all its state machines) | Handler, MO, Legal, Admin |
| **Submit** | submit a claim to the engine | Handler, MO |
| **Payments** | assemble → approve → pay batches | Handler (assemble), Admin (approve/pay) |
| **Cases** | investigation/review case machine (REVIEW / BLOCK / CLAWBACK) | Handler (REVIEW), Investigator (BLOCK/CLAWBACK) |
| **Disputes** | the objection register (s91) | Handler, MO, Legal |
| **Audit** | post-payment clawback recovery | Investigator |
| **Accidents** | the accident graph + convergence | all (Investigator reads) |
| **Intelligence** | party fraud analytics (providers/attorneys/claimants/fairness/sweep) | Investigator |
| **Coding** | tariff/NAPPI leakage, negotiation targets, condition cost bands | all (analytics) |
| **Governance** | precision/recall, promotions, fairness, ground-truth labels | Admin (acts), all (view) |
| **Reference** | the L0 reference data — tariff, NAPPI, ICD-10, comparable awards | all |
| **Reasons** | the reason register — every rule the engine can fire | all |
| **Notifications** | the POPIA-minimal outbox + channel preferences | operators |
| **Admin** | users, config, reference tiers, signal modes, audit log | Admin |

---

## 12. Troubleshooting

**"forbidden for role …" / a button is greyed with "Requires role: X".** Your role can't perform that action. Check the matrix (§4); the tooltip names the role(s) that can. Ask an ADMIN, or hand off to the right role.

**A transition button isn't showing at all.** The action isn't *legal* from the entity's current state (state machines only offer valid transitions), not a permission issue. Check the state chip.

**A claim won't pay ("held").** Read its **holds** (§3). Each names the blocker: validate the documents, accept merits, verify the payee, confirm attorney standing, or resolve its disposition. Clear the hold, and it becomes eligible.

**"different approver required" on a payment.** Segregation of duties: the admin approving a batch must not be the one who assembled it. Have a different admin approve.

**An offer won't include general damages.** It's `gated_by` serious injury — a Medical Officer must create and accept a RAF 4 assessment first (§6.1).

**I promoted a signal but nothing changed.** Signal-mode changes are effective-dated reference data; confirm the effective date and that the signal isn't `GROUNDED` (those are locked `SCORED`). The change is audit-logged in Admin → Audit.

**A `GREEN` claim is in the `FRAUD` lane.** Band and disposition are independent — one low-weight fraud feature routes it to review without moving the score. That's correct behaviour; work the case.

---

## 13. Glossary

- **Band** — the risk triage score bucket: `GREEN` (0–24) / `AMBER` (25–49) / `RED` (50+).
- **Disposition** — the worst-wins routing lane: `FRAUD` > `MERITS` > `COMPLIANCE` > `PREAUTH` > `SI_GATE` > `ADJUSTED` > `CLEAN`.
- **Eligibility / hold** — whether a claim can pay, and if not, why.
- **OAR** — the official accident report (the case number); a universal mandatory document.
- **Merits** — liability: was the Fund at fault, and by how much (the fault %)?
- **Serious injury (RAF 4)** — the gate that unlocks general damages (list match / WPI ≥ 30% / narrative test).
- **Undertaking** — the Fund's promise to pay defined future treatment; invoices are billed against it.
- **The six heads** — past medical, future medical, loss of earnings, loss of support, general damages, funeral. The offer's components.
- **Case** — a unit of human investigation/review work: lane (REVIEW/BLOCK/CLAWBACK) + priority (SLA) + verdict.
- **Dispute** — a lodged objection to a determination; reconsidered internally or referred out.
- **Batch** — a set of payment instructions assembled, approved, and paid together.
- **Signal / reason** — a named rule the engine fires; its register entry fixes its weight, category, maturity, and mode.
- **Mode (`SHADOW`/`ADVISORY`/`SCORED`)** — whether a signal is silent, visible, or scoring.
- **Maturity (`GROUNDED`/`HEURISTIC`/`UNVALIDATED`)** — the evidentiary grade of a signal; `GROUNDED` is law-cited and always scores.
- **Convergence** — how independently corroborated an accident is (0–100).
- **Segregation of duties** — the rule that the assembler, approver, and payer of money must differ.

---

*Roles and actions above are taken from the code: `server/api/*.py` role guards, the state-machine actor roles in `server/*_service.py`, and the workflow permission map in `ui/src/components/Workflow.tsx`. ADMIN is a superuser throughout. For how the engine scores risk, read [how-risk-is-determined.md](how-risk-is-determined.md) and [how-party-risk-is-determined.md](how-party-risk-is-determined.md).*
