"""Reference rails client — sign an RCJ claim and submit it to a running RIE server, then
verify the fund's signed receipt. This is the integrator's starting point.

Usage (with the server running, e.g. `PORT=8077 ./run.sh`):
    RAILS_URL=http://localhost:8077 python3 conformance/rails_client.py
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import jws  # noqa: E402

SECRET = os.environ.get("RIE_RAILS_SECRET", "rie-rails-dev-secret")
BASE = os.environ.get("RAILS_URL", "http://localhost:8077").rstrip("/")

CLAIM = {
    "claim_id": f"RCJ-{uuid.uuid4().hex[:8]}", "claim_type": "SUPPLIER",
    "party_token": "P_demo", "accident_date": "2026-02-01", "lodged_on": "2026-03-01",
    "case_number_raw": "CAS 4242/02/2026", "payee_verified": True,
    "documents": {"RAF2": True, "OAR": True, "INVOICES": True, "BANK": True},
    "lines": [{"kind": "TARIFF", "code": "0190", "qty": 1, "amount": 800.0,
               "service_date": "2026-03-01", "provider_id": "PR_demo", "dx": "S72"}],
}


def submit(body: dict) -> dict:
    header = {"alg": "HS256", "jti": str(uuid.uuid4()), "exp": int(time.time()) + 300}
    signature = jws.sign_detached(header, body, SECRET)                 # detached JWS over the body
    req = urllib.request.Request(
        f"{BASE}/rails/v1/claims", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Idempotency-Key": str(uuid.uuid4()),
                 "X-JWS-Signature": signature}, method="POST")
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def main() -> None:
    out = submit(CLAIM)
    print(json.dumps(out, indent=2))
    receipt = dict(out["receipt"])
    sig = receipt.pop("signature")
    ok = jws.verify_detached(sig, receipt, SECRET) is not None
    print(f"\nfund receipt signature valid: {ok}")
    print(f"verdict: {out['verdict']['outcome']}  payableNow: R{out['verdict']['payableNow']:.2f}"
          f"  repricedOff: R{out['verdict']['repricedOff']:.2f}")


if __name__ == "__main__":
    main()
