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

Dev logins (username == password): `admin`, `handler`, `medical`, `investigator`, `legal`.

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
