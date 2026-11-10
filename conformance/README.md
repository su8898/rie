# Provider channel — conformance kit

Connect a practice-management system or a switch to the Fund's provider channel, and prove the
connection is correct, in an afternoon.

| File | What it is |
| --- | --- |
| `refclient.py` | The reference client. Self-contained (standard library plus `cryptography`). Copy it. |
| `runner.py` | The conformance runner. Seventeen protocol checks against a running Fund endpoint. |
| `rails_client.py` | The older shared-secret demo client. Development only. |

The interface itself is specified in [`docs/provider-interface.md`](../docs/provider-interface.md).

## 1. Make a key pair

```bash
python3 conformance/refclient.py keygen my-key.pem
```

This writes your **private** key to `my-key.pem` and prints your **public** key as a JWK. Keep the
private key secret. Send the Fund only the public key, with the party id you want to sign as and
the provider ids (practice numbers) you bill for. The Fund registers it under Admin → Channel keys.

## 2. Certify

```bash
python3 conformance/runner.py --base https://fund.example --party MY-PARTY --key my-key.pem \
    --provider 0265691
```

`--provider` must be one your party is registered for. `--code` and `--amount` set the tariff line
used in the test claims. The run submits a handful of small claims, so point it at a sandbox.

A pass ends with `17/17 checks passed — CONFORMANT` and exit code 0. Any failure names the check
and exits 1.

## What it checks

- **Keys.** The Fund publishes its signing key.
- **Claims.** A signed claim is accepted and answered. The receipt carries the Fund's genuine
  signature. A retry with the same `Idempotency-Key` returns the same submission, and the same key
  with a different body is refused.
- **Refusals.** A replayed signature, a body that does not match its signature, an unsigned
  request, an expired signature, an unregistered key id, and a claim for a provider outside the
  party's scope are each refused.
- **Reads.** A submission and a claim's status can be read back. A read signed for a different
  subject is refused, and another provider's remittances cannot be listed.
- **Batch and switch message.** A batch is answered claim by claim with a repeat deduplicated, and
  a BHF XML message is scored like any claim.

The verdict's content is not asserted, because it depends on the Fund's reference data.
