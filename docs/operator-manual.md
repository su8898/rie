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
| **Payments** — new run / add or remove a claim / edit note / cancel an open run | ✓ | | | | ✓ |
| **Payments** — approve | | | | | ✓ (not the assembler) |
| **Payments** — release payment / cancel an approved run | | | | | ✓ (release: not the assembler or the approver) |
| **Audit** — recovery sweep / review / recover / clear | | | ✓ | | ✓ |
| **Governance** — view precision / recall / labels | any | any | any | any | any |
| **Governance** — draw QA reviews into Cases | any | any | any | any | any |
| **Governance** — apply a signal-mode promotion | | | | | ✓ (sole) |
| **Admin** — users, caps, negotiated, pre-auth, signal modes | | | | | ✓ (sole) |

---

## 5. Role guide: Handler

**You are the claims caseworker** — the workhorse of the Fund. You take a claim from submission through validation, merits, offer, and settlement, and you assemble the batches that pay it.

**Your pages:** Claims (New claim) → Claim record (Workflow tab) · Cases (REVIEW lane) · Payments · Disputes · plus all the read-only analytics.

### 5.1 Capture and read a claim

1. Go to **Claims** and choose **New claim**. The form has four parts: the claim (reference, type, claimant, accident and lodgement dates, police case number), liability (personal claims only), supporting documents, and the medical account.
2. **Claimant:** enter a 13-digit identity number or an existing claimant reference. An identity number is replaced by an anonymous reference and is never stored.
3. **Supporting documents:** the checklist follows the claim type. A supplier claim needs the RAF 2 form, the accident report, invoices and banking details. A personal claim needs the RAF 1 form, the accident report, an identity document and banking details. The summary on the right names anything still outstanding; the claim is held until it arrives.
4. **Medical account:** one row per billed line (tariff or medicine code, quantity, amount, service date, practice number, diagnosis). Leave the discipline blank to take it from the practice register.
5. **Submit claim.** Fields that need attention are marked before anything is sent. The engine prices and assesses the claim and you land on its record.
6. On **Claims**, use the saved views (Ready to pay, Held, Pricing review, Fraud review), the filters (type, risk, status, practice, lodged dates) and the search. Click a column heading to sort. **Export** downloads the filtered list (up to 200 claims) as a CSV file. Filters live in the page address, so a filtered list can be bookmarked or shared.
7. Click a row to open the **claim record**. Its tabs are Overview (what is holding the claim and each finding), Lines (billed, reference and payable per line with the reason for every reduction), Documents, Payments, Workflow, History (every determination) and Technical.

Invoices against an undertaking are captured from the claim record: **Workflow → Undertakings**.

### 5.2 Drive the lifecycle (Claim record → Workflow)

The claim record's **Workflow** tab shows where the claim is on its path (Lodged, Validated, Merits, Quantum, Offer made, Settled, Paid, Finalised) and the **Next steps** available. Each step opens a confirmation that says what it does before you take it. A step you may not take is greyed out, and hovering over it says which role can.

- **Validate lodgement** once the documents are complete, or **Reject lodgement** if it does not comply.
- **Open merits**, then in **Merits** choose **Accept liability** (entering the claimant's share of fault, which reduces every head) or **Reject liability** (choosing the ground). **Move to quantum** is refused until liability is accepted.
- **Build offer**: past medical expenses come from the adjudicated account. Tick the other heads that apply (loss of earnings, loss of support, general damages, funeral expenses) and enter the amounts. For general damages, choose the injury to compare against past awards, or enter the range by hand. The offer shows each head, the total, and anything holding it.
- **Make the offer**, then **Record settlement** (you or Legal). A settled claim becomes payable in a payment run; **Mark as paid** is for a payment made outside a run and is an administrator's step.
- **Finalise** once paid.

Beside the path, the tab holds **Serious-injury assessments**, **Undertakings** with their invoices, and **Litigation**. **Workflow history** at the foot lists every step on the claim, across all of these, with who took it.

### 5.3 Work a billing-review case

**Cases** opens on what is still open. The views across the top (Open, Assigned to me, Unassigned, Past due, Escalated, Closed) carry counts; search by case number, claim, reason or person, filter by kind, and sort by priority, due date or amount at stake. A *Billing review* case is yours; a *Fraud hold* or a *Recovery* belongs to the investigators.

1. **Open a case**: choose the kind, a reason, the priority (Urgent to Lowest, which sets the due date) and optionally the claim and the amount at stake. The claim reference is checked before the case is opened.
2. Click a case to open its record. **Take this case** assigns it to you. Add **Notes** as you work; a note cannot be changed once added. **Edit** corrects the priority, reason or amount while the case is open; changing the priority resets the due date.
3. **Close case** asks for the outcome, what was found, and any amounts recovered or prevented. A closed case cannot be reopened or changed. If it needs the fraud team, **Escalate**: it moves to the investigators' queue and only an investigator can close it.

The **History** tab lists every step and every edit with who made it. If a button is greyed out, the line under the header says which role owns the case.

Your verdict on close becomes a **ground-truth label** that tunes the engine (governance precision/recall). Judge the merits honestly.

### 5.4 Assemble a payment run

**Payments** has three lists: **Payment runs**, **Ready to pay** and **Remittance advice**. The figures at the top show what is ready to pay and how many runs are waiting at each step.

1. Open **Ready to pay**. It lists every claim cleared for payment that has not been paid, with how it will be paid and the amount. A claim that cannot be added says why (for example it is already in a run).
2. Tick the claims and choose **Add to a payment run**. Pick a run that is still being assembled, or a new one. You land on the run.
3. On the run, **Claims in this run** shows what will be paid. While the run is being assembled you can **Remove** a claim (it goes back to Ready to pay), **Edit note**, or use **Add claims** for more. **Another payment** on that tab captures an interim payment, or a settlement or court order by claim reference; the Fund checks the claim and the amount before it accepts it.
4. Hand over. The **Three-person control** panel shows who assembled, approved and released the run, and tells you why a button is not available to you. You cannot approve or release a run you assembled.

**History** on the run lists every change with who made it. A cancelled run pays nothing and cannot be reopened.

---

## 6. Role guide: Medical Officer

**You are the clinical authority.** Two things are yours alone: the **serious-injury (RAF 4)** gate that unlocks general damages, and the **undertakings** that pre-authorise future treatment (and their invoices). You can also submit and assess claims and take part in dispute reconsiderations.

**Your pages:** Claims (New claim) · Claim record (Workflow → Serious injury, Undertakings) · Disputes · analytics.

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

### 7.1 Find who to look at (Party intelligence)

**Party intelligence** compares each practice and attorney with others like it (see [how-party-risk-is-determined.md](how-party-risk-is-determined.md)). A rating is a reason to look closer, never a verdict.

- **Practices** and **Attorneys**: a rating (Low, Watch, Elevated, High, Critical) and a score out of 100, with search, filters and sorting. **How it is scored** shows the four parts of the score. A party with fewer than 5 claims is not rated. Click a practice to open its record.
- **Repeat claimants**: a claimant who is a party to two or more accidents.
- **Fairness**: whether findings fall evenly across groups of practices. A group flagged much more or much less than the rest is marked for a look.
- **High-risk list**: every practice and attorney at or above a score you choose, highest first. **It only lists.** Being on it holds no claim and opens no case; to act on a party, open a case (next step).

### 7.2 Work a fraud-hold or recovery case

In **Cases**, the *Fraud hold* (stop a suspect claim) and *Recovery* (recover a paid one) kinds are yours, as is the **Escalated** view:

1. **Open a case** on the flagged claim, or pick up an escalated case from the handlers.
2. **Take this case**, investigate, keep **Notes**, and **Close case** with an outcome (Fraud confirmed, Cleared, Payment adjusted, No action needed or Referred to legal), what was found, and the amounts recovered or prevented. Escalated cases are closed by you.

### 7.3 Post-payment recovery (Audit)

**Recovery audit** lists paid claims that now look wrong. **Find paid claims to review** opens an item for each paid claim that was paid on a high-risk assessment or billed by a practice at or above the risk score you set; a claim that already has an item is skipped. Per item: **Start review** to pick it up, then **Record recovery** (the amount returned, which cannot be more than was paid, and an outcome: recovered in full, in part, written off or not pursued) or **Clear** if the payment was correct. The views (Not started, Under review, Recovered, Cleared) carry counts. The **recovery rate** (recovered against paid) is the realised return of the whole integrity effort.

### 7.4 Undertakings

You can **suspend** and **resume** an active undertaking when an investigation warrants it (with the Medical Officer).

---

## 8. Role guide: Legal

**You are the legal team** — the escalation path for anything contested. You refer disputes out, run litigation, and handle merits and serious-injury appeals.

**Your pages:** Disputes · Claim detail (Workflow → Merits, Serious injury, Litigation, Lifecycle) · analytics.

### 8.1 Disputes (the objection register)

**Disputes** lists every objection to a decision of the Fund. It opens on what is still open; the views (Open, New, Past deadline, Referred, All) carry counts, and you can search by dispute number, claim or grounds and filter by what is disputed, who raised it and status. Anyone can **Lodge a dispute**: the claim reference is checked, and the grounds are required. Each dispute opens as its own record, with the steps available to you shown as buttons:

- Handler, Medical Officer or Legal chooses **Start reconsideration**, then **Uphold** or **Reject**. Both ask for the reasons, which the objector sees. **Edit grounds** corrects what was captured; the earlier wording stays in the history.
- **Referral is yours alone.** **Refer** sends a serious-injury dispute to the **HPCSA tribunal** and anything else to **litigation**, where a litigation matter is opened and linked. After the external outcome, **Record outcome** closes the dispute. A dispute may be **withdrawn** at any open stage.

The **History** tab lists every step with who took it.

### 8.2 Litigation

When a claim is repudiated or a dispute is litigated, drive the matter on the claim's **Workflow → Litigation** panel: **open litigation**, then **plead → set trial → judgment** (or **settle**), or **default judgment**. ADMIN records **order-paid**; you (or ADMIN) **close** the matter. In the **Lifecycle** panel you also drive **litigate**, **court-order**, and **settle**.

### 8.3 Merits and serious-injury appeals

- **Merits:** you can **accept**/**reject** (with a Handler) and, after a rejection, **appeal** it — then **accept** or **dismiss** the appeal.
- **Serious injury:** you **appeal** a rejected RAF 4 assessment and **uphold** or **dismiss** that appeal (the tribunal path).

---

## 9. Role guide: Admin

**You run the console and you hold the money keys.** Admin has two hats: the **configuration authority** (users, statutory config, reference tiers, signal modes) and the **payment authority** (approve and pay). Admin is also a superuser — so use it deliberately.

**Your pages:** Admin · Practices (maintain the register) · Payments (approve, release) · Governance (apply promotions) · everything else.

### 9.1 Administration

**Administration** is a set of pages with a side menu grouped by purpose: **Access** (Users, Channel access), **Pricing** (Dated rates, Negotiated rates), **Rules** (Statutory cap, Pre-authorisation codes, Coding rules, Signal modes) and **Oversight** (Audit log). Each page has its own address, a search or filter, and a **Recent changes** panel showing who last changed that setting. Every change is audit-logged; it is reference data, never a code deploy. Actions that remove something or cut off access ask you to confirm first.

- **Users** — **Add user**, **Change role**, **Reset password**, **Deactivate** or **Reactivate**. A user is never deleted: a person who leaves is deactivated, so their name stays on what they did. You cannot deactivate the account you are signed in as, and the system refuses any change that would leave no active administrator. A new password must be at least 8 characters and is given to the user directly.
- **Signal modes** — how much weight each finding carries: *Shadow* (measured only), *Advisory* (shown, not scored) or *Scored*. The **Suggested** column is what measured precision recommends (Governance computes it); choose **Change**, pick the mode and give a reason. **Reset** returns a finding to its default. Findings marked *Set by law* (`GROUNDED`) are always scored and cannot be changed: you cannot switch off the law. Filter by mode, or show only findings with a suggested change.
- **Statutory cap** — the s17(4)(c) annual cap on loss of income and support, by the date each amount takes effect. The engine applies the cap in force on the **date of the accident**, so earlier entries must stay. The page marks which entry is in force today. Add, edit the amount, or remove an entry.
- **Pre-authorisation codes** — the tariff codes that are paid only when treatment was authorised beforehand. Add or remove a code.
- **Negotiated rates** — a price agreed for one code, paid instead of the gazetted tariff (the engine prices `min(billed, negotiated)`). Add, edit or remove. A code that has dated versions is maintained under Dated rates, and the page says so.
- **Dated rates** — the reference tariff, negotiated rates and medicine exit prices as dated versions. The engine pays each line at the rate in force on its **service date**, so late claims price at the tariff of their day. A rate is never deleted: it is replaced from a date, corrected, or ended.
  - **Find a rate:** pick the price list (Reference tariff, Negotiated, Medicine exit price), search by the start of the code, filter by discipline, and set **Rates as at** to see what was in force on any date.
  - **Rate history:** click a code. It lists every version, newest first. **New rate** sets a rate from a date (the earlier rate ends the day before; the date must be later than every existing version). **Increase** applies a percentage from a date. **Correct** fixes a capture error on one version and needs a note. **End** closes an open-ended rate on a last day and needs a note.
  - **Add rate** captures a rate for a code that may not have one yet. **Increase** in the page header raises every matching rate by a percentage: choose the list, the percentage, the date and an optional code prefix and discipline, then review the summary before applying. Codes that already have a version on or after the date are skipped and listed.
  - **Import** loads a CSV file (`code, rate, effective_from`, optionally `discipline, kind, source, note`); bad rows are reported and do not stop the rest. **Export** downloads the list as at the chosen date.
  - **Change log** lists every new, corrected or ended rate with the old and new amount and who made the change.
- **Price lists** — their own page under **Reference**; any operator can read them, an administrator maintains them. A price list is one edition of a tariff kept as it was published: its entries, its edition, where it was published and its **legal standing** (*Enforceable*, *Accepted* or *Interdicted*). **A price list is a record. It does not change what a claim is paid:** claims are priced from Dated rates.
  - **Create a list:** **New price list** asks for a name, edition, where it was published, the date it takes effect and its legal standing. It starts as a **draft**.
  - **Add its entries:** open the draft. **Add entry** captures one figure: a code, the discipline it sits in, the price column (for example *specialist*; use *standard* when there is only one), a description, units and a rand value. Leave units or the rand value empty if the list does not print it. Enter codes exactly as the list prints them. **Load from a file** loads a CSV file with a header row; choose whether to keep the entries already there or remove them first. Rows that cannot be read are listed and the rest still load. Amounts take a point or a single comma as the decimal mark, and an amount with both is refused.
  - **Find an entry:** search by the start of a code or by words in the description, and filter by discipline, price column, and whether a rand value, units only, or no figure is printed. **Export** downloads the whole list.
  - **Publish:** a draft needs at least one entry, a start date and a source. Publishing fixes the list. After that only its notes can be edited.
  - **Correct or update a published list:** **New edition** creates a draft with the same entries. Change what differs and publish it. The earlier edition stays as it was.
  - **Change legal standing:** when a court sets a tariff aside or restores it, **Change legal standing** records the new standing with the reason. This is allowed on a published list.
  - **Retire:** ends a published list on a date. A retired list is kept and cannot be changed. Only a draft can be deleted.
  - **Overview** shows the list's details, its conversion factors (rand per unit, recorded as the list states them and applied to nothing), its price columns and a count per discipline. **History** shows every change with who made it.
- **Coding rules** — the tariff's own billing rules per code. *Once per encounter*: a repeat for the same claimant, provider and day is not paid (`UNBUNDLING_CONFLICT`). *Time* rules: the billed quantity is minutes and the line is priced by its ladder off the block rate, not per minute. *Percentage of time*: a share of the anaesthetic-time lines billed with it; with none on the claim the line goes to review. The reference loader seeds the list from the tariff; a rule you set here is kept on reload. Check the seeded once-only codes against the gazette, because the descriptions were read by OCR.
- **Channel access** — who may connect to the provider channel. Each connecting party (a provider's own system, or a switch) signs its requests with a private key only it holds; you register the matching **public** key here, with the provider ids the party may act for. A switch may be given `*` for any provider. **Suspend** refuses a party's signatures at once. Never accept or paste a private key: the form refuses one, and a party that sent one must generate a new pair. **Practices** changes which practice numbers a system may act for, and **Replace key** swaps its public key (the old key is refused at once). Both were API-only before. A system is never deleted; suspend it to cut it off.
- **Audit log** — every change made in Administration and to the practice register: who, what and when. Filter by area, person, subject and date; **Show record** reveals the stored entry; **Export** downloads the filtered entries as a CSV file. Entries cannot be edited or removed.
- **Practice register** — now its own page, **Practices** (under Providers); any operator can read it, an administrator maintains it. It records who each billing practice is, by practice number: its name, discipline, setting and status. The register decides three things at claim intake, whatever the submitter put on the claim. A **suspended** or **deregistered** practice cannot bill: its claims carry `PROVIDER_UNREGISTERED` and payment is blocked. A practice's lines are priced under its **registered discipline**, so a practice cannot claim a dearer one. And its **setting** decides whether a claim counts as a hospital account. The banner at the top says whether enforcement is on; while it is off, a practice that is not in the register is accepted as submitted. Changing the register does not alter claims already decided.
  - **Find a practice:** the views (All, Active, Suspended, Deregistered) carry counts; search by practice number, name, discipline or council number; filter by discipline, setting, type and verification; click a column heading to sort. **Export** downloads the filtered list as a CSV file.
  - **Not in the register:** this view lists every practice number that is billing the Fund without an entry, the largest biller first, with its claims and billed total. **Add to register** opens the form with the number filled in.
  - **Add or import:** **Add practice** captures one entry. **Import** loads a CSV file (choose a file or paste rows); good rows are loaded, bad rows are listed by line, and an import never changes a practice's status.
  - **The practice record:** click a practice to open it. It shows the register entry, what the practice has billed and been paid, its billing risk, and tabs for its Claims, Remittance advice, Channel access (the systems that may sign for it) and History (every change, with who made it). **Edit details** changes the entry; the practice number itself cannot be changed.
  - **Suspend, deregister, reinstate:** these are on the practice record. Barring a practice needs a reason, which is shown on the record and logged. There is no delete: a practice that should no longer bill is deregistered, so its history is kept.
- **Audit** — the append-only log of every admin mutation.

### 9.2 Approve and pay (the money keys)

**Medical reports.** A provider files the RAF 1 medical report and the RAF 4 serious injury assessment electronically. They appear on the claim's page under **Medical reports on file**, each with a **Print** page and an **XML** document. The two chips at the top show, per form, whether one is on file and whether a complete one is. A report marked *Incomplete* lists the required fields the provider left empty; ask the provider to file a corrected report. When a complete RAF 4 arrives for a personal claim with no serious-injury assessment, the assessment is opened for the Medical Officer automatically, carrying the form's impairment percentage and narrative finding.

When a run is released, the system issues a **remittance advice** for each practice paid in it. They are listed on the run's **Remittance advice** tab and under **Payments → Remittance advice**, where you can search by advice reference, practice or claim and filter by status and service period. Each advice opens as its own record: every claim and line billed, what was paid and why any line was reduced, with a **Print** page and an **XML** document. Providers fetch and acknowledge their own advice over the rails channel, and the status changes to *Acknowledged* when they do. An advice never shows a review or fraud signal. A provider's objection to a reduction arrives in **Disputes** with *raised by PROVIDER*.

In **Payments**, administrators are the second and third pair of hands. Open a run from **Payment runs** (the *Being assembled* and *Approved, awaiting release* views show what is waiting). **Approve** a run someone else assembled; after approval its contents are fixed. A third person then chooses **Release payment**, which pays the claims and issues the remittance advice. The person who assembled a run cannot approve it, and neither the assembler nor the approver can release it. Administrators are the sole authority for releasing a run, lifecycle `pay`, undertaking-invoice `pay`, and litigation `order-paid`.

### 9.3 Close the governance loop

**Signal governance** shows how often each finding was borne out on closed cases. **Suggested changes** lists the findings whose record supports a different mode: more weight once we can be confident at least 60% of its cases bore it out, less when it falls short. **Apply** makes the change and asks for a reason (it is the same edit as Administration → Signal modes, and is audit-logged); once applied, the suggestion goes away. **What the engine misses** shows the miss rate measured from automatically cleared claims that were re-checked; **Open quality checks** opens blind billing-review cases to keep that figure honest. **Case outcomes** lists the closed cases all of this is measured from, with a download.

---

## 10. The claim's journey — how the roles hand off

A single claim can pass through every role. Here is the end-to-end path and who does each step:

```
                    ┌─────────────────────────────────────────────────────────┐
   HANDLER /        │  1. INTAKE — capture the claim (New claim)               │
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
| **Dashboard** | what is waiting for attention (cases, disputes, payments, notifications), each a link into its worklist; then the book of claims: risk mix and where claims stand | all |
| **Claims** | the claims worklist — saved views, filters, sorting, export; open a claim's record | all (Handler acts) |
| **Claim record** | one claim in tabs: Overview, Lines, Documents, Payments, **Workflow** (all its state machines), History, Technical | all (Handler, MO, Legal, Admin act) |
| **New claim** | capture a claim; it is priced and assessed on submission | Handler, MO |
| **Payments** | payment runs (assemble → approve → release), the ready-to-pay list and remittance advice; each run and each advice opens as a record | Handler (assemble), Admin (approve, release) |
| **Practices** | the practice register and each practice's record; practice numbers billing without an entry | all read, Admin maintains |
| **Cases** | the case worklist and each case's record: take, note, edit, escalate, close | Handler (billing review), Investigator (fraud hold, recovery) |
| **Disputes** | the dispute worklist and each dispute's record: reconsider, uphold, reject, refer, record the outcome | Handler, MO, Legal |
| **Recovery audit** | paid claims to review: find them, review, record a recovery or clear | Investigator |
| **Accidents** | every accident with its claims, claimants against occupants reported, and how well independent sources support it; filter to accidents with several claims, thin support or more claimants than reported | all (Investigator reads) |
| **Party intelligence** | ratings for practices and attorneys, repeat claimants, fairness across groups, and a high-risk list | Investigator (all can read) |
| **Coding analysis** | spend by code (reduced, paid above reference, no reference price), rates worth negotiating, the usual cost of treating each injury with an amount checker, and practices whose prices are rising | all (read-only) |
| **Signal governance** | how reliable each finding has proved, suggested mode changes, what the engine misses, and the case outcomes behind the figures | Admin (applies), all (read) |
| **Reference data** | look up a tariff rate, a medicine price, a diagnosis code (by code or by words in the diagnosis) or the comparable awards for an injury; the Overview tab shows which lists are loaded | all |
| **Price lists** | whole tariff editions kept as published, with their source and legal standing; each list opens as a record with its entries, overview and history. A record only: claims are priced from Dated rates | all read, Admin maintains |
| **Reason catalogue** | every finding the engine can raise: what it leads to, whether it blocks or reduces payment or adds to the risk score, its mode, its evidence and its basis; filter by any of these | all |
| **Notifications** | messages to claimants by status, with search and filters; mark a message sent or failed; **Claimant consent** records whether and how a claimant may be contacted | operators |
| **Admin** | users, config, reference tiers, signal modes, audit log | Admin |

---

## 12. Troubleshooting

**"forbidden for role …" / a button is greyed with "Requires role: X".** Your role can't perform that action. Check the matrix (§4); the tooltip names the role(s) that can. Ask an ADMIN, or hand off to the right role.

**A transition button isn't showing at all.** The action isn't *legal* from the entity's current state (state machines only offer valid transitions), not a permission issue. Check the state chip.

**A claim won't pay ("held").** Read its **holds** (§3). Each names the blocker: validate the documents, accept merits, verify the payee, confirm attorney standing, or resolve its disposition. Clear the hold, and it becomes eligible.

**Approve or Release payment is greyed out.** Three-person control: the person who assembled a run cannot approve it, and neither the assembler nor the approver can release it. The line under the Three-person control panel says which rule applies. Have a different administrator act.

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
- **Payment run** (batch) — a set of payments assembled, approved and released together. Each line in it is a payment instruction for one claim.
- **Signal / reason** — a named rule the engine fires; its register entry fixes its weight, category, maturity, and mode.
- **Mode (`SHADOW`/`ADVISORY`/`SCORED`)** — whether a signal is silent, visible, or scoring.
- **Maturity (`GROUNDED`/`HEURISTIC`/`UNVALIDATED`)** — the evidentiary grade of a signal; `GROUNDED` is law-cited and always scores.
- **Convergence** — how independently corroborated an accident is (0–100).
- **Segregation of duties** — the rule that the assembler, approver, and payer of money must differ.

---

*Roles and actions above are taken from the code: `server/api/*.py` role guards, the state-machine actor roles in `server/*_service.py`, and the workflow permission map in `ui/src/components/Workflow.tsx`. ADMIN is a superuser throughout. For how the engine scores risk, read [how-risk-is-determined.md](how-risk-is-determined.md) and [how-party-risk-is-determined.md](how-party-risk-is-determined.md).*
