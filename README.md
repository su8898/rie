# RIE — RAF Integrity Engine

A claims-integrity platform for South African **Road Accident Fund** claims. Greenfield build;
the COIDA "CIE" system is a reference blueprint only, never forked. This repo currently
implements the **scoring spine end-to-end**: a claim is ingested, anchored to the accident
graph, corroborated, gated, adjudicated line-by-line, scored, disposed, and checked for payment
eligibility — then persisted and served over a JSON API to a React operator UI.

## The load-bearing idea: the engine has an executable spec

[`spec/rie_engine.py`](spec/rie_engine.py) is the complete decision path as one deterministic,
side-effect-free function. The [`engine/`](engine) package is that spec expanded into real
modules. [`tests/test_conformance.py`](tests/test_conformance.py) runs a shared scenario matrix
through **both** and asserts the determination records are identical — so the engine can never
silently drift from its specification. Everything above the engine (persistence, API, UI) is a
thin shell around it.

## Architecture

```
React SPA (ui/)  ──/api──►  FastAPI JSON API (server/)  ──►  engine/ (pure-stdlib decision path)
     Vite/Tailwind            routers → services → ORM            │  validated against
                                    │                             ▼  spec/rie_engine.py (oracle)
                             PostgreSQL 16 / SQLite
                        reference · corpus · operational
```

- **`engine/`** — the decision path, pure stdlib, zero third-party deps. One module per
  domain-logic section (benchmark, accidents, corroboration, gates, adjudication, heads,
  scoring, disposition, payments, pipeline).
- **`server/`** — FastAPI. `routers → services → models`. One shared reference resolver; the app
  reads the immutable corpus and writes operational tables.
- **`ui/`** — React 19 + React Router 7 + Tailwind (Vite).
- **DB** — SQLite by default (hermetic tests + local run); PostgreSQL 16 in production (set
  `RIE_DATABASE_URL`). Canonical DDL in [`db/schema.sql`](db/schema.sql).

## Quickstart

```bash
# 1. Tests (hermetic — SQLite, no services needed)
python3 -m pytest -q                     # engine unit tests + conformance + API integration

# 2. Backend  (http://localhost:8021)
./run.sh                                 # or: uvicorn server.main:app --port 8021

# 3. Frontend (http://localhost:5173, proxies /api → :8021)
cd ui && npm install && npm run dev
```

Dev logins (username == password, **dev/test only** — never seeded when `RIE_APP_ENV=prod`):
`admin`, `treasury` (second ADMIN — the payer), `handler`, `medical`, `investigator`, `legal`.
Payments need three different people: a HANDLER assembles, one ADMIN approves, another pays.

**Secrets.** `RIE_SECRET_KEY`, `RIE_RAILS_SECRET`, `RIE_PSEUDONYM_SECRET` have dev defaults; with
`RIE_APP_ENV=prod` the API refuses to start unless each is set to ≥32 random characters, and the
first ADMIN is bootstrapped from `RIE_BOOTSTRAP_ADMIN_PASSWORD`. See `db/.env.example`.

## Deployment (Docker + PostgreSQL + real reference data)

The stack runs on one command: PostgreSQL 16, a one-shot **reference loader** that seeds the RAF
reference snapshot (`reference.db` — ~540k NAPPI prices, 1,367 gazetted tariffs, 41k ICD-10)
into Postgres, then the API (serving the built SPA + JSON API + provider rails on one port).

```bash
cd db && docker compose up --build          # db + loader + api
open http://localhost:8021                    # the operator console
```

`reference.db` (at the repo root) is bind-mounted into the loader and mapped into RIE's
reference tables ([`db/load_reference.py`](db/load_reference.py)): tariffs → the ACCEPTED
tariff reference (claims pay `min(billed, rate)`), NAPPI → SEP (+dispensing fee), ICD-10 →
diagnoses. Claims are then priced against the **real** rates — e.g. tariff `10190` → R587.24,
NAPPI Traumeel → R43.54 SEP+fee. Browse it at `/api/reference/{tariffs,nappi,icd10,editions}`.

To load reference data into any target DB directly (SQLite or Postgres):
`RIE_DATABASE_URL=... python3 db/load_reference.py`.

## Dated reference rates

The payment-rule rates — the tariff by discipline (`RPL`), negotiated rates and the NAPPI single
exit price (`SEP`) — are append-only **versions** ([`server/rates_service.py`](server/rates_service.py),
ported from CIE's effective-dated rate store). A new rate from a later date supersedes the prior
version (closed the day before); the engine prices every line at the version in force on its
**service date** (`engine.rate_on`), so a late claim pays at the tariff of its day and an increase
never reprices history. A key without versions keeps its undated row from the loader, in force on
every date; its first dated change materialises that row as the `baseline` version.

Maintain them under **Admin → Dated rates** or over `/api/rates` (ADMIN): add / supersede,
percentage increase (one key or every key in a filter), correct, retire, CSV import and export.
Maintenance is forward-only and every change writes `ref_rate_log` and the admin audit log.
Existing databases need `alembic upgrade head` (migration `d4b7e2a91c35`).

## Coding rules and billing signals

Ported from CIE's coding rules and scorer signals; specified first in `spec/rie_engine.py` (§4b, §7b).

**Coding rules** are the tariff's own billing rules, held per tariff code in `ref_code_rule` and read
through `RefBook.code_rules` ([`engine/coding.py`](engine/coding.py)):

| Rule | Effect at adjudication |
| --- | --- |
| `ONCE_PER_ENCOUNTER` | The first use for a claimant, provider and day is paid. A repeat, at any amount and on any claim, is paid nothing with `UNBUNDLING_CONFLICT`. |
| `TIME_BLOCK` | Quantity is minutes. One block per `param` minutes or part thereof (emergency theatre time, 0011). |
| `TIME_ANAES` | Quantity is minutes. One block per 15 minutes or part in the first hour, 1.5 blocks per 15 minutes after (0023). |
| `TIME_FIRST_HOUR` | Quantity is minutes. One block for the first hour, then a third per 15 minutes or part (0039). |
| `PCT_OF_TIME` | `param` share of the anaesthetic-time lines billed by the same provider on the same day (0018, 0019). With no such line the modifier is `REFERENCE_UNRESOLVED` and goes to review. |

`python3 db/load_reference.py` seeds the once-only codes from the tariff descriptions and the standard
time modifiers the tariff carries. It also loads CIE's list of codes that must not be priced at a flat
rate (percentage modifiers, cost-of-material codes) into `ref_non_bench`, so those lines go to review.
Code 3575 is excluded from the once-only seed because its wording was misread from a neighbouring code. Maintain them under **Admin → Coding rules** or over
`/api/admin/code-rules` (ADMIN); a rule set by hand survives a reload. **Before go-live, confirm with
RAF that time-modifier quantities are billed in minutes, and review the seeded once-only list: the
descriptions are OCR text.**

**Billing signals** ([`engine/signals.py`](engine/signals.py)) are soft features. They score and never
reprice a line. An encounter is one provider treating the claimant on one day. Thresholds are
`Ruleset` fields.

| Signal | Fires when | Launch mode |
| --- | --- | --- |
| `LINE_COUNT_OUTLIER` | 12 or more lines on one encounter | advisory |
| `MATERIAL_PADDING` | 12 or more NAPPI lines forming 60% or more of one encounter | advisory |
| `IMPOSSIBLE_DAY` | one provider bills 30 or more claimants on one day | advisory |
| `IMPOSSIBLE_WEEK` | 8 or more encounters are billed for one claimant in one ISO week | advisory |
| `PROVIDER_SHOPPING` | 3 or more providers of one discipline bill one claimant | shadow |

The thresholds were calibrated on COIDA claims, so the four advisory signals (`LAUNCH_ADVISORY`)
are shown to reviewers but carry no points and never hold a payment. Promote one to scored under
**Admin → Signal modes** once Governance shows its precision on RAF claims.

The day and week screens skip a claim submitted with `"facility": true` (a hospital account). The
server supplies the cross-claim counts (`pipeline_service.billing_activity`). **Coding → Price drift**
(`GET /api/coding/drift`) ranks providers whose billed ÷ reference ratio rises month on month.
Existing databases need `alembic upgrade head` (migration `e5c8f3b0a246`).

## Remittance advice and provider lookups

Ported from CIE's remittance advice and its interface-standard profiles. Nothing here changes the engine.

**Remittance advice** ([`server/remittance_service.py`](server/remittance_service.py)). When a
payment batch is paid, each provider paid in it gets one advice: every adjudicated line with billed,
paid and reduced, and the reason for a reduction. Lines come from the stored adjudication and are
reconciled to the cent to the amount actually paid, so an apportioned payment is spread pro rata and
marked `PAYMENT_ADJUSTED`. Only payment-rule reasons are shown; a review or fraud signal is never
disclosed. Only `SUPPLIER` and `UNDERTAKING_INVOICE` instructions remit. Formats: JSON, a
`<Remittance>` XML document and a print page. Operators see them under **Payments → Remittance
advice**; an ADMIN can issue for a batch paid earlier with `POST /api/remittances/issue/{batch_id}`.

**Provider lookups** ([`server/provider_service.py`](server/provider_service.py)) on the rails channel:

| Method | Path | Signed over | Purpose |
| --- | --- | --- | --- |
| GET | `/rails/v1/status/{claim_id}` | `{"claimId"}` | Outcome, billed, payable, payment status and remittance references. No band, score or signal. |
| POST | `/rails/v1/registration/lookup` | the body | Whether a personal claim is registered for a claimant, and whether the supplied accident date and police case number match it. A raw identity number is tokenised and never stored or echoed. |
| GET | `/rails/v1/remittances?provider_id=` | `{"providerId"}` | A provider's advices, optionally by service period. |
| GET | `/rails/v1/remittances/{ref}` | `{"remittanceRef"}` | The full advice. `?format=xml` returns the XML document. |
| POST | `/rails/v1/remittances/{ref}/ack` | `{"remittanceRef"}` | The provider confirms receipt and reconciliation. |
| POST | `/rails/v1/objections` | the body, with a one-time `jti` | Lodge an objection (`TARIFF`, `QUANTUM` or `REPUDIATION`). It lands in the dispute register. A late one is recorded and flagged, not refused. |
| GET | `/rails/v1/objections/{ref}` · `?provider_id=` | `{"objectionRef"}` · `{"providerId"}` | Poll one objection, or list a provider's. |

A read accepts the party's detached JWS over the subject shown, or an operator session. An
expired signature is refused. Each party signs with its own key and is scoped to its providers
(see **Provider channel: keys, intake and conformance** below). Existing databases need
`alembic upgrade head` (migration `f6d9a4c1b357`).

## Medical reports

Ported from CIE's statutory medical report forms and adapted to the Fund's own
([`server/medical_report_service.py`](server/medical_report_service.py)). Nothing here changes the engine.

A provider's system files a completed form over the rails channel. The Fund stores it against the
claim reference it quotes, exactly as filed (sections → fields → label and value), and both sides
can read and print it.

| Form code | Form | Basis |
| --- | --- | --- |
| `RAF1-MR` | The medical report in the RAF 1 claim form, by the treating practitioner | Act s24(2)(a) |
| `RAF4` | The serious injury assessment report | Regulation 3 |

- **The Fund judges completeness.** Every field the catalogue marks required must carry a value. The response and the print page name what is missing.
- **A complete RAF 4 opens the serious-injury assessment.** On a personal claim with no assessment yet, it is created `SUBMITTED` for the medical officer with the form's impairment figure and narrative finding.
- **A report may arrive before its claim.** It is stored unresolved and tied to the claim the first time the claim's reports are asked for.
- **No patient identity on the wire.** The patient is identified by the claim reference. A bare 13-digit identity number anywhere in a filing is refused.
- **Filing is idempotent and replay-protected.** It needs an `Idempotency-Key` and a signed body with a one-time `jti`.

| Method | Path | Signed over | Purpose |
| --- | --- | --- | --- |
| GET | `/rails/v1/medical-reports/forms` | `{"catalogue": "medical-report-forms"}` | The form catalogue and its required fields. |
| POST | `/rails/v1/medical-reports` | the body | File a report. |
| GET | `/rails/v1/medical-reports/{ref}` · `?provider_id=` | `{"reportRef"}` · `{"providerId"}` | Read one (`?format=xml` for XML), or list a provider's. |
| GET | `/rails/v1/claims/{claim_id}/documentation` | `{"claimId"}` | Which forms are on file for a claim and whether a complete one is among them. |

Operators see the reports under **Claim detail → Medical reports on file**, with a print page and
the XML document, over `/api/medical-reports`. **The field lists are working layouts. Check them
against the gazetted RAF 1 and RAF 4 before go-live; a layout change is an edit to `FORMS`.** CIE's
rule that holds payment until a first medical report arrives was not ported: it is tied to COIDA
modifiers and has no RAF equivalent. Existing databases need `alembic upgrade head`
(migration `a7e2c5d8f419`).

## Provider channel: keys, intake and conformance

Ported from CIE's provider-intake standard. The full interface is specified in
[`docs/provider-interface.md`](docs/provider-interface.md).

- **A signing key per party.** A provider's system, or a switch, signs every request with its own
  ES256 private key. The Fund holds only the public key, registered under **Admin → Channel keys**
  (`/api/admin/rails-parties`), so a signature identifies its signer
  ([`server/rails_auth.py`](server/rails_auth.py)). Suspending a party or rotating its key takes
  effect at once.
- **Provider scope on every route.** A party acts only for the provider ids registered against it.
  A claim for another provider is `403`; another provider's record looks like one that does not exist.
- **The Fund signs back.** Receipts are signed with the Fund's ES256 key, published at
  `/rails/v1/.well-known/jwks.json`. Set `RIE_RAILS_SIGNING_KEY` (PEM) in production; unset, a key
  is generated at start-up and changes on restart.
- **Switch messages.** `POST /rails/v1/claims/switch` takes a BHF `<Claims>` XML message inside the
  signed envelope and scores it like any claim ([`server/switch_intake.py`](server/switch_intake.py)).
- **Batches.** `POST /rails/v1/batches` takes up to 100 claims, answers each on its own, and
  deduplicates a claim the party already sent ([`server/rails_batch_service.py`](server/rails_batch_service.py)).
- **Conformance kit.** [`conformance/`](conformance/README.md) holds a self-contained reference
  client and a runner with seventeen protocol checks.

```bash
python3 conformance/refclient.py keygen my-key.pem
python3 conformance/runner.py --base http://localhost:8077 --party MY-PARTY --key my-key.pem --provider PR0001
```

**The shared secret is off in production.** It identifies nobody, so outside dev and test it is
refused unless `RIE_RAILS_ALLOW_SHARED_SECRET=1` is set. ES256 needs the `cryptography` package
(now in `requirements.txt`). Existing databases need `alembic upgrade head` (migration `b8f3d6e9a520`).
Not ported: EDIFACT intake, CIE's gateway with per-switch traffic logs, and its switch console.

## The practice register

Ported from CIE's provider identity registry ([`server/provider_registry_service.py`](server/provider_registry_service.py)).
It is a local, administrator-maintained register keyed on the practice number, standing in for the
BHF practice-number register until a live feed is granted. Nothing here changes the engine: at claim
intake the register sets three fund-side facts that a submitter must not assert for itself.

| Fact | Rule |
| --- | --- |
| Registration | A practice marked `SUSPENDED` or `DEREGISTERED` may not bill. The claim is `PROVIDER_UNREGISTERED` and payment is blocked, whatever the payload says. |
| Discipline | A verified row's discipline is the one its lines are priced under. The submitter's value is kept as `discipline_asserted`. |
| Setting | A claim whose practices are all registered as a hospital or emergency unit is a facility account. One whose practices are all rooms-based is not. |

A practice the register does not know leaves the claim as submitted. Set
`RIE_PROVIDER_REGISTER_ENFORCED=1` to refuse unknown practices too, but only once the register is
loaded, or every claim is held. The facts are fixed at submission: a rescore does not re-read the
register. Maintain it under **Admin → Practice register** or over `/api/admin/practices` (add,
update, status with a reason, CSV import); any operator can read `/api/practices`. `RegisterFeed`
is the seam for a live feed and is inert today. Existing databases need `alembic upgrade head`
(migration `c9a4e7f1b632`).

## API

| Method | Path | Notes |
|---|---|---|
| GET | `/healthz` | liveness + DB check |
| POST | `/api/auth/login` · `/logout` · GET `/me` | session cookie |
| POST | `/api/claims` | submit → score → persist (roles HANDLER/MEDICAL_OFFICER) |
| GET | `/api/claims?band=&disposition=` | determinations list |
| GET | `/api/claims/{id}` | claim + latest determination |
| GET | `/api/accidents` · `/{id}` | accident graph with live convergence |
| GET | `/api/reasons` | reason catalogue (code, maturity, basis, mode) |
| GET | `/api/dashboard` | band/disposition mix, exposure, eligibility |
| GET | `/api/rates?source=&q=&on=` · `/versions` · `/log` · `/export` | rate in force on a date, version history, change trail, CSV |
| POST | `/api/rates` · `/increase` · `/bulk-increase` · `/import` · `/{id}/adjust` · `/{id}/retire` | dated rate maintenance (ADMIN) |
| GET · POST · DELETE | `/api/admin/code-rules` · `/api/admin/code-rules/{code}` | coding rules per tariff code (ADMIN) |
| GET | `/api/coding/drift?min_months=&min_lines=` | providers whose billing ratio is rising |
| GET | `/api/remittances?provider_id=` · `/{ref}` · `/{ref}/xml` · `/{ref}/print` | remittance advice: list, detail, XML, print page |
| POST | `/api/remittances/issue/{batch_id}` | issue advice for a paid batch that has none (ADMIN) |
| GET | `/api/practices?q=&status=` · `/summary` · `/{provider_id}` | the practice register: list, counts, one practice's identity |
| POST | `/api/admin/practices` · `/import` · `/{provider_id}/status` | maintain the practice register (ADMIN) |
| GET | `/api/medical-reports?claim_id=&provider_id=` · `/forms` · `/documentation/{claim_id}` · `/{ref}` · `/{ref}/xml` · `/{ref}/print` | medical reports on file: list, catalogue, per-claim status, detail, XML, print page |

A determination record: `{claim_id, accident_id, accident_action, convergence, validated,
band, score, reasons[], shadow_signals[], disposition, medical_payable, net_payable,
eligible_to_pay, holds[], engine_version, ruleset_effective, reference_edition}`.

## Engine modules (→ domain-logic §)

| Module | Does | §-ref |
|---|---|---|
| `reference.py` | benchmark resolver, `(rate, src, legal_status)` | §3 |
| `accidents.py` | CAS normalisation + entity resolution | §6.0 |
| `corroboration.py` | convergence, independence-weighted | §6.0 |
| `gates.py` | prescription · s24 · standing · merits | §4 |
| `adjudication.py` | line reconcile / reprice / refer + pre-auth | §3, §5f |
| `heads.py` | past medical · Sweatman cap · general damages | §5 |
| `scoring.py` | reasons → points → band (+ signal modes) | §10, §11 |
| `disposition.py` | worst-wins category | §9 |
| `payments.py` | eligibility + holds | §8e |
| `pipeline.py` | `process_claim` — the brain, end to end | §11 |

## Status

**Built & verified:** the scoring spine end-to-end (engine + conformance oracle + JSON API +
persistence + accident graph + React UI). **Next** (per `../RAF_Claims/BUILD-PLAN.md`):
heads-of-damage offer builder, the merits / serious-injury / undertaking / litigation state
machines, party intelligence, leakage accounting, and the RCJ submission rails.
