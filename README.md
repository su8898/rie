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
