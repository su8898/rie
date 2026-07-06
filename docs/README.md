# RIE documentation

Operator- and reviewer-facing documentation for the RAF Integrity Engine. Every document is written **from the code** (the engine `engine/` mirrored by the oracle `spec/rie_engine.py`, and the services under `server/`) — where a document and the code disagree, the code is correct.

The spec itself (`domain-logic.md`, `SPECIFICATION.md`) lives with the spec; these are the explainers that sit on top of the implementation.

## Read in this order

1. **[how-risk-is-determined.md](how-risk-is-determined.md)** — *claim-level risk.* How one submitted claim becomes a risk verdict: the three independent axes (band = triage score, disposition = worst-wins routing, eligibility = payment gate), the reason register, the `SHADOW → ADVISORY → SCORED` mode lifecycle, the exact `score_and_band` algorithm, convergence, and worked examples. **Start here** — everything else builds on it.

2. **[how-party-risk-is-determined.md](how-party-risk-is-determined.md)** — *party-level risk.* How a provider / attorney / claimant is scored across all its claims: the four-component 0–100 composite, cohort-relative and n-guarded, the read-only risk sweep, and the fairness self-check. Includes the **claim-axis → party-aggregate diagram** (§1) — the clearest single view of how claim risk rolls up into party risk.

3. **[operator-manual.md](operator-manual.md)** — *how to operate it, by role.* The five roles (Handler / Medical Officer / Investigator / Legal / Admin), a full capability matrix, per-role step-by-step guides, the end-to-end claim journey and its hand-offs, a page reference, troubleshooting, and a glossary.

## The two risk surfaces at a glance

| | Claim-level | Party-level |
|---|---|---|
| **Unit** | one claim | one actor (provider / attorney / claimant) |
| **Output** | band · disposition · eligibility | a 0–100 composite score + rating |
| **Effect** | gates and prices a payment | ranks actors for review — opens no gate |
| **Doc** | how-risk-is-determined.md | how-party-risk-is-determined.md |

Party risk is **emergent from** claim risk: a party's score is an aggregate of the per-claim determinations its claims produced.

---

*Source of truth: the code. `§` references point to `domain-logic.md`. If a doc drifts from the engine, regenerate it from the engine.*
