"""Seed a corpus that exercises the Intelligence + Audit pages: varied providers (one with
flagged claims), attorneys, a recurring claimant, paid claims, and opened clawback items.
Run after (or instead of) seed_demo.  python3 db/seed_intel.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import audit_service as aud, payments_service as pay  # noqa: E402
from server.db import SessionLocal  # noqa: E402
from server.pipeline_service import assess_and_store  # noqa: E402
from server.seed import init_db  # noqa: E402

H = {"username": "handler", "role": "HANDLER"}
A = {"username": "admin", "role": "ADMIN"}
I = {"username": "investigator", "role": "INVESTIGATOR"}


def sup(cid, party, cas, provider, dx="S72", dx_regions=None, attorney=None, amount=500.0,
        accident_date="2026-02-01", lodged_on="2026-03-01"):
    p = {"claim_id": cid, "claim_type": "SUPPLIER", "party_token": party,
         "accident_date": accident_date, "lodged_on": lodged_on, "case_number_raw": cas,
         "today": "2026-07-05", "payee_verified": True,
         "documents": {"RAF2": True, "OAR": True, "INVOICES": True, "BANK": True},
         "lines": [{"kind": "TARIFF", "code": "0190", "qty": 1, "amount": amount,
                    "service_date": accident_date, "provider_id": provider, "dx": dx}]}
    if dx_regions:
        p["accident_dx_regions"] = dx_regions
    if attorney:
        p["attorney"] = attorney
    return p


def main() -> None:
    init_db()
    with SessionLocal() as db:
        clean = []
        for i in range(3):                                   # PR_BAD: flagged (dx-mismatch)
            assess_and_store(db, sup(f"R_ib{i}", f"P_ib{i}", f"CAS 980{i}/02/2026", "PR_BAD",
                                     dx="K35", dx_regions=["S72"], attorney="Dubious & Co"))
        for i in range(4):                                   # PR_BAD: clean (will be paid)
            cid = f"R_ic{i}"
            assess_and_store(db, sup(cid, f"P_ic{i}", f"CAS 981{i}/02/2026", "PR_BAD",
                                     attorney="Dubious & Co"))
            clean.append(cid)
        for i in range(5):                                   # PR_GOOD: clean
            assess_and_store(db, sup(f"R_ig{i}", f"P_ig{i}", f"CAS 982{i}/02/2026", "PR_GOOD",
                                     attorney="Honest LLP"))
        for i in range(3):                                   # PR_SPEC: high value -> SPECIALIST
            assess_and_store(db, sup(f"R_is{i}", f"P_is{i}", f"CAS 983{i}/02/2026", "PR_SPEC",
                                     amount=1200.0))
        # recurring claimant across two DISTINCT accidents (different dates so they don't merge)
        assess_and_store(db, sup("R_ir1", "P_IREC", "CAS 9840/02/2026", "PR_GOOD"))
        assess_and_store(db, sup("R_ir2", "P_IREC", "CAS 9841/06/2024", "PR_GOOD",
                                 accident_date="2024-06-15", lodged_on="2024-07-01"))

        b = pay.create_batch(db, H, note="PR_BAD supplier run")   # pay PR_BAD's clean claims
        for cid in clean:
            pay.add_instruction(db, b.id, cid, "SUPPLIER", None, H)
        pay.approve(db, b.id, A)
        pay.pay(db, b.id, A)
        opened = aud.recovery_sweep(db, I, threshold=20)          # -> clawback items on PR_BAD

        print(f"intel seeded: PR_BAD (flagged) / PR_GOOD / PR_SPEC providers, "
              f"attorneys Dubious&Co + Honest LLP, 1 recurring claimant, "
              f"{len(clean)} paid, {len(opened)} audit items opened")


if __name__ == "__main__":
    main()
