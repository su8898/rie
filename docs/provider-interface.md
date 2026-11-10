# RIE provider interface — version 1

How a provider's system, or a switch acting for providers, exchanges claims and their paperwork
with the Fund. This is the Road Accident Fund edition of the interface standard built for CIE.
Every route is under `/rails/v1`. A machine-readable description of all routes is served at
`/openapi.json`.

## 1. Parties and keys

A **party** is one connecting system: a provider's own practice-management system, or a switch.
Each party:

1. generates an ECDSA P-256 key pair (`conformance/refclient.py keygen`),
2. sends the Fund its **public** key, a party id, and the provider ids it acts for,
3. is registered by a Fund administrator (Admin → Channel keys).

The Fund never holds a party's private key. A provider system is registered for the practice
numbers it bills under. A switch may be registered for a list, or for any provider.

## 2. Signing

Every request carries `X-JWS-Signature`: a detached JWS, `base64url(header)..base64url(signature)`.

- **Algorithm:** `ES256`. The header names the party's key: `{"alg": "ES256", "kid": "<party id>"}`.
- **What is signed:** the canonical JSON (sorted keys, no whitespace) of the request body for a
  `POST`, or of the request's **subject** for a `GET` — for example `{"claimId": "R-1"}`.
- **`exp`** is required and may be at most 900 seconds ahead. An expired signature is refused.
- **`jti`**, a one-time value, is required on every write. A repeated `jti` is refused.

The Fund signs each claim receipt with its own ES256 key. Its public key is published, unsigned,
at `GET /rails/v1/.well-known/jwks.json`; the receipt's header names the key id.

## 3. Scope

After verifying a signature the Fund checks that the party may act for the provider concerned.

| Request | Rule | If not |
| --- | --- | --- |
| A claim, batch entry or switch message | every line's provider is in the party's scope | `403` |
| A request that names a provider (`provider_id`) | that provider is in scope | `403` |
| A read by reference (submission, claim, advice, objection, report) | the record belongs to a provider in scope | `404` |

A record a party may not see is indistinguishable from one that does not exist.

## 4. Reliability

- **Idempotency.** Every write that creates something carries `Idempotency-Key`. The same key and
  body returns the stored answer with `idempotentReplay: true`. The same key with a different
  body, or from another party, is `409`.
- **Batches.** `{"claims": [...]}`, up to 100. Each claim is answered on its own; one bad claim
  does not fail the file. A claim the party already submitted returns its stored verdict with
  `deduplicated: true`.

## 5. Routes

| Method and path | Signed over | Purpose |
| --- | --- | --- |
| `POST /claims` | body | Submit one claim. Returns the verdict and a signed receipt. |
| `POST /claims/switch` | body | Submit a BHF XML message: `{"format": "BHF_XML", "message": "<Claims>…"}`. |
| `POST /batches` | body | Submit up to 100 claims. |
| `GET /batches/{batchId}` | `{"batchId"}` | Read a batch back (its sender only). |
| `GET /claims/{submissionId}` | `{"submissionId"}` | Read a submission back. |
| `GET /status/{claimId}` | `{"claimId"}` | Outcome, payable, payment status, remittance references. |
| `POST /registration/lookup` | body | Is a claim registered for this claimant, and do the supplied details match? |
| `GET /remittances?provider_id=` | `{"providerId"}` | A provider's remittance advices. |
| `GET /remittances/{ref}` | `{"remittanceRef"}` | One advice (`?format=xml` for XML). |
| `POST /remittances/{ref}/ack` | `{"remittanceRef"}` | Confirm receipt and reconciliation. |
| `POST /objections` | body | Lodge an objection to a determination. |
| `GET /objections/{ref}` · `?provider_id=` | `{"objectionRef"}` · `{"providerId"}` | Poll one, or list a provider's. |
| `GET /medical-reports/forms` | `{"catalogue": "medical-report-forms"}` | The form catalogue. |
| `POST /medical-reports` | body | File a RAF 1 medical report or a RAF 4. |
| `GET /medical-reports/{ref}` · `?provider_id=` | `{"reportRef"}` · `{"providerId"}` | Read one, or list a provider's. |
| `GET /claims/{claimId}/documentation` | `{"claimId"}` | Which forms are on file for a claim. |
| `GET /.well-known/jwks.json` | not signed | The Fund's public signing key. |

## 6. A BHF XML message

The message is the `<Claims>` document a practice system or switch already produces. The Fund reads:

| Element | Use |
| --- | --- |
| `ClaimHeader/BhfNumber/Treating` (or `Supplier`) | the billing provider |
| `ClaimHeader/ClaimNbr` (or `Account/AccountNbr`) | the claim reference |
| `ClaimHeader/Patient/IdNumber` | the claimant — tokenised on receipt, never stored |
| `ClaimHeader/Date/Service`, `Date/Created` | service date, lodgement date |
| `ClaimHeader/ClaimDiagnosis/Code` | the diagnosis |
| `ClaimHeader/Header/PlaceOfService` | hospital codes mark the claim as a facility account |
| **`ClaimHeader/AccidentDate`** | **RAF extension, required**: the date of the accident |
| **`ClaimHeader/CaseNumber`** | **RAF extension**: the police case number |
| `Item/Procedure/Tariff`, `Quantity`, `Item/ItemFinancials/Total` | one billing line |
| `Item/LineType` = `NAPPI` or `MEDICINE`, `Procedure/Nappi` | a medicine or material line |
| `Item/ServiceDate` | a line's own service date, when it differs |

A message carries no document checklist, so the claim is scored and then held until the Fund
confirms its supporting documents. A `DOCTYPE` or `ENTITY` declaration is refused.

## 7. Errors

| Status | Meaning |
| --- | --- |
| `400` | `Idempotency-Key` or `jti` missing |
| `401` | signature missing, invalid, expired, or from an unknown or suspended key |
| `403` | the party may not act for the provider named |
| `404` | no such record, or not this party's |
| `409` | idempotency key reused, signature replayed, or claim already submitted |
| `422` | the body is malformed |

## 8. Not in this version

EDIFACT messages, a gateway with per-switch traffic logs, and hosted portal screens. The shared
HS256 secret of earlier versions still verifies in development and test; production accepts
registered party keys only unless `RIE_RAILS_ALLOW_SHARED_SECRET=1` is set.
