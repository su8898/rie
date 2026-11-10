"""Conformance runner — certify a party's connection to the RIE provider channel in one command.

It drives the channel with the reference client and checks the security and reliability rules
an integration relies on: signed requests, the Fund's signed receipt, idempotent retry, replay
and tamper rejection, expiry, provider scoping, read-back, batch and switch-message intake. The
verdict's content is not asserted (it depends on the Fund's reference data); the protocol is.

    python3 conformance/runner.py --base http://localhost:8077 --party MY-PARTY --key my-key.pem \\
        --provider PR0001

The party must be registered with the Fund and allowed to act for `--provider`. The run submits
a handful of small test claims, so point it at a sandbox.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import refclient  # noqa: E402

FOREIGN_PROVIDER = "PR-NOT-REGISTERED-TO-THIS-PARTY"


def _claim(provider: str, code: str, amount: float) -> dict:
    tag = uuid.uuid4().hex[:10]
    return {"claim_id": f"CONF-{tag}", "claim_type": "SUPPLIER", "party_token": f"P_conf_{tag}",
            "accident_date": "2026-02-01", "lodged_on": "2026-03-01",
            "case_number_raw": f"CAS {int(tag[:4], 16) % 9000 + 1}/02/2026",
            "documents": {"RAF2": True, "OAR": True, "INVOICES": True, "BANK": True},
            "lines": [{"kind": "TARIFF", "code": code, "qty": 1, "amount": amount,
                       "service_date": "2026-03-01", "provider_id": provider, "dx": "S72"}]}


def _bhf(provider: str, code: str, amount: float) -> str:
    tag = uuid.uuid4().hex[:10]
    return (f"<Claims><Document><ClaimHeader><BhfNumber><Treating>{provider}</Treating></BhfNumber>"
            f"<ClaimNbr>CONF-X{tag}</ClaimNbr><Date><Service>20260301</Service><Created>20260305</Created></Date>"
            f"<Patient><IdNumber>{int(tag, 16) % 10**13:013d}</IdNumber></Patient>"
            f"<ClaimDiagnosis><Code>S72</Code></ClaimDiagnosis><AccidentDate>20260201</AccidentDate>"
            f"</ClaimHeader><Item><Procedure><Tariff>{code}</Tariff><Quantity>1</Quantity></Procedure>"
            f"<ItemFinancials><Total>{amount:.2f}</Total></ItemFinancials></Item></Document></Claims>")


def run(client: "refclient.Client", provider: str, *, code: str = "0190", amount: float = 100.0,
        out=print) -> list[tuple[str, bool, str]]:
    """Run every check. Returns [(name, passed, detail)]."""
    results: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail="") -> None:
        results.append((name, bool(ok), str(detail)))
        out(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not ok else ""))

    out("keys:")
    try:
        keys = client.fund_keys()
    except Exception as e:                              # noqa: BLE001 — any failure is a failed check
        keys = {}
        check("the Fund publishes its signing key", False, e)
    else:
        check("the Fund publishes its signing key", bool(keys) and all(k.get("crv") == "P-256" for k in keys.values()))

    out("claims:")
    claim, key = _claim(provider, code, amount), str(uuid.uuid4())
    status, first = client.post("/rails/v1/claims", claim, idem=key)
    ok = status == 200 and "verdict" in first and "receipt" in first
    check("a signed claim is accepted and answered with a verdict", ok, f"{status} {first}")
    sid = first.get("submissionId") if ok else None
    check("the receipt carries the Fund's genuine signature", ok and client.receipt_is_genuine(first["receipt"]))

    status, again = client.post("/rails/v1/claims", claim, idem=key)
    check("a retry with the same key returns the same submission",
          status == 200 and again.get("submissionId") == sid and again.get("idempotentReplay") is True,
          f"{status} {again}")
    status, _ = client.post("/rails/v1/claims", {**claim, "lodged_on": "2026-03-02"}, idem=key)
    check("the same key with a different body is refused", status == 409, status)

    fresh = _claim(provider, code, amount)
    signature = refclient.sign(client.key, client.party_id, fresh)
    status, _ = client.post("/rails/v1/claims", fresh, signature=signature)
    replay_status, _ = client.post("/rails/v1/claims", fresh, signature=signature)
    check("a replayed signature is refused", status == 200 and replay_status == 409, f"{status} then {replay_status}")

    other = _claim(provider, code, amount)
    status, _ = client.post("/rails/v1/claims", other, signature=refclient.sign(client.key, client.party_id, fresh))
    check("a body that does not match its signature is refused", status == 401, status)
    status, _ = client.send("POST", "/rails/v1/claims", other, {"Idempotency-Key": str(uuid.uuid4())})
    check("an unsigned request is refused", status == 401, status)
    expired = refclient.sign(client.key, client.party_id, other, lifetime=-10)
    status, _ = client.post("/rails/v1/claims", other, signature=expired)
    check("an expired signature is refused", status == 401, status)
    stranger = refclient.sign(client.key, f"unknown-{uuid.uuid4().hex[:6]}", other)
    status, _ = client.post("/rails/v1/claims", other, signature=stranger)
    check("an unregistered key id is refused", status == 401, status)
    status, _ = client.post("/rails/v1/claims", _claim(FOREIGN_PROVIDER, code, amount))
    check("a claim for a provider outside the party's scope is refused", status == 403, status)

    out("reads:")
    status, back = client.get(f"/rails/v1/claims/{sid}", {"submissionId": sid})
    check("the submission can be read back", status == 200 and back.get("submissionId") == sid, status)
    status, st = client.get(f"/rails/v1/status/{claim['claim_id']}", {"claimId": claim["claim_id"]})
    check("the claim's status can be read", status == 200 and st.get("outcome") in ("CLEAN_PASS", "REPRICED", "HELD"),
          f"{status} {st}")
    status, _ = client.get(f"/rails/v1/status/{claim['claim_id']}", {"claimId": "something-else"})
    check("a read signed for a different subject is refused", status == 401, status)
    status, _ = client.get(f"/rails/v1/remittances?provider_id={FOREIGN_PROVIDER}", {"providerId": FOREIGN_PROVIDER})
    check("another provider's remittances cannot be listed", status == 403, status)

    out("batch and switch message:")
    new = _claim(provider, code, amount)
    status, batch = client.post("/rails/v1/batches", {"claims": [new, claim]})
    results_ = batch.get("results", []) if status == 200 else []
    check("a batch is answered claim by claim, and a repeat is deduplicated",
          len(results_) == 2 and results_[0].get("status") == 200 and results_[0].get("deduplicated") is False
          and results_[1].get("deduplicated") is True, f"{status} {batch}")
    status, sw = client.post("/rails/v1/claims/switch", {"format": "BHF_XML", "message": _bhf(provider, code, amount)})
    check("a BHF XML switch message is accepted and answered with a verdict",
          status == 200 and "verdict" in sw, f"{status} {sw}")
    return results


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", required=True, help="the Fund's base URL, e.g. http://localhost:8077")
    ap.add_argument("--party", required=True, help="your registered party id (the JWS kid)")
    ap.add_argument("--key", required=True, help="path to your ES256 private key (PEM)")
    ap.add_argument("--provider", required=True, help="a provider id your party may act for")
    ap.add_argument("--code", default="0190", help="a tariff code to bill in the test claims")
    ap.add_argument("--amount", type=float, default=100.0)
    a = ap.parse_args(argv)
    client = refclient.Client(refclient.http_transport(a.base), a.party, refclient.load_key(a.key))
    started = time.time()
    results = run(client, a.provider, code=a.code, amount=a.amount)
    passed = sum(1 for _n, ok, _d in results if ok)
    verdict = "CONFORMANT" if passed == len(results) else "NOT CONFORMANT"
    print(f"\n{passed}/{len(results)} checks passed in {time.time() - started:.1f}s — {verdict}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
