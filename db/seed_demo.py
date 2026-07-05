"""Populate a spread of determinations so the UI/dashboard have realistic content.

Run against a fresh DB:  rm -f rie.db && python3 db/seed_demo.py
Drives the real pipeline (assess_and_store), so it also serves as a broad smoke test.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.db import SessionLocal          # noqa: E402
from server.pipeline_service import assess_and_store  # noqa: E402
from server.seed import init_db             # noqa: E402

TODAY = "2026-07-05"


def line(code="0190", amount=500.0, kind="TARIFF", dx="S72", qty=1,
         svc="2026-03-01", provider="PR1", emergency=False):
    return {"kind": kind, "code": code, "qty": qty, "amount": amount,
            "service_date": svc, "provider_id": provider, "dx": dx, "emergency": emergency}


def supplier(cid, party, cas, lines, **kw):
    return {"claim_id": cid, "claim_type": "SUPPLIER", "party_token": party,
            "accident_date": "2026-02-01", "lodged_on": "2026-03-01", "case_number_raw": cas,
            "today": TODAY, "payee_verified": True,
            "documents": {"RAF2": True, "OAR": True, "INVOICES": True, "BANK": True},
            "lines": lines, **kw}


def personal(cid, party, cas, lines, **kw):
    return {"claim_id": cid, "claim_type": "PERSONAL", "party_token": party,
            "accident_date": "2026-02-01", "lodged_on": "2026-03-01", "case_number_raw": cas,
            "today": TODAY, "payee_verified": True,
            "documents": {"RAF1": True, "OAR": True, "ID": True, "BANK": True},
            "lines": lines, **kw}


def undertaking(cid, party, cas, lines, ceiling, **kw):
    return {"claim_id": cid, "claim_type": "UNDERTAKING_INVOICE", "party_token": party,
            "accident_date": "2026-02-01", "lodged_on": "2026-03-01", "case_number_raw": cas,
            "today": TODAY, "payee_verified": True,
            "documents": {"INVOICES": True, "BANK": True},
            "undertaking": {"active": True, "scope_dx": ["S72"], "scope_coded": True,
                            "authorisations": [{"codes": ["0190"], "qty_limit": 10,
                                                "ceiling": ceiling, "valid_from": "2026-01-01",
                                                "valid_to": "2026-12-31"}]},
            "lines": lines, **kw}


DEMO = [
    supplier("R_1001", "P_1001", "CAS 1001/02/2026", [line(amount=500)]),                 # CLEAN
    supplier("R_1002", "P_1002", "CAS 1002/02/2026", [line(amount=800)]),                 # ADJUSTED (reprice)
    supplier("R_1003", "P_1003", "CAS 1003/02/2026", [line(code="0200", amount=400)]),    # interdicted signal
    supplier("R_1004", "P_1004", "CAS 1004/02/2026", [line(amount=500), line(amount=500)]),  # DUPLICATE_LINE
    supplier("R_1005", "P_1005", "CAS 1005/02/2026", [line(amount=500)], provider_registered=False),
    personal("R_2001", "P_2001", "CAS 2001/02/2026", [line(amount=500)], merits_accepted=None),
    personal("R_2002", "P_2002", "CAS 2002/02/2026", [line(amount=500)], merits_accepted=True, fault_pct=0),
    personal("R_2003", "P_2003", "CAS 2003/02/2026", [line(amount=500)], merits_accepted=True, fault_pct=25),
    personal("R_2004", "P_2004", "CAS 2004/02/2026", [line(amount=500)], merits_accepted=False, merits_ground="S19_EXCLUSION"),
    personal("R_2005", "P_2005", "CAS 2005/02/2026", [line(amount=500)], merits_accepted=True,
             accident_date="2020-01-01", lodged_on="2024-01-01"),                          # prescribed
    personal("R_2006", "P_2006", "CAS 2006/02/2026", [line(amount=500)], merits_accepted=True,
             documents={"RAF1": False, "OAR": True, "ID": True, "BANK": True}),            # s24 incomplete
    personal("R_2007", "P_2007", "CAS 2007/02/2026", [line(dx="K35", amount=500)],
             merits_accepted=True, accident_dx_regions=["S72"]),                            # DX mismatch (FRAUD)
    undertaking("R_4001", "P_4001", "CAS 4001/02/2026", [line(amount=500)], ceiling=1000),  # within auth
    undertaking("R_4002", "P_4002", "CAS 4002/02/2026", [line(amount=500)], ceiling=300),   # PREAUTH_EXCEEDED
    supplier("R_3001", "P_3001", "CAS 3050/03/2026", [line(svc="2026-03-11")],
             accident_date="2026-03-10", lodged_on="2026-03-20"),                           # accident A
    supplier("R_3002", "P_3002", "CAS 3050/03/2026", [line(svc="2026-03-11")],
             accident_date="2026-03-10", lodged_on="2026-03-20"),                           # joins A
]


def main() -> None:
    init_db()
    with SessionLocal() as db:
        print(f"{'claim':10} {'band':6} {'disp':11} {'act':10} {'pay':>9}  holds")
        for p in DEMO:
            r = assess_and_store(db, p)
            print(f"{r['claim_id']:10} {r['band']:6} {r['disposition']:11} "
                  f"{r['accident_action']:10} {r['net_payable']:>9.2f}  {','.join(r['holds'])}")


if __name__ == "__main__":
    main()
