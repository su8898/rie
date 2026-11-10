"""Drive one claim (R_SHOW) through every state machine so the UI workflow panel is fully
populated — for demos/screenshots. Run after seed_demo (or standalone; it seeds base data)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import (  # noqa: E402
    lifecycle_service as lc, litigation_service as lit, merits_service as mer,
    serious_injury_service as si, undertaking_service as und,
)
from server.db import SessionLocal  # noqa: E402
from server.offers_service import persist_offer  # noqa: E402
from server.pipeline_service import DuplicateClaim, assess_and_store as _assess  # noqa: E402


def assess_and_store(db, payload, **kw):
    """Re-run tolerant: a claim already in the corpus is skipped (the API would answer 409)."""
    try:
        return _assess(db, payload, **kw)
    except DuplicateClaim:
        db.rollback()
        return None
from server.seed import init_db  # noqa: E402

H = {"username": "handler", "role": "HANDLER"}
M = {"username": "medical", "role": "MEDICAL_OFFICER"}
L = {"username": "legal", "role": "LEGAL"}

CID = "R_SHOW"
CLAIM = {
    "claim_id": CID, "claim_type": "PERSONAL", "party_token": "P_SHOW",
    "accident_date": "2026-02-01", "lodged_on": "2026-03-01",
    "case_number_raw": "CAS 7000/02/2026", "today": "2026-07-05", "payee_verified": True,
    "documents": {"RAF1": True, "OAR": True, "ID": True, "BANK": True},
    "lines": [{"kind": "TARIFF", "code": "0190", "qty": 1, "amount": 800.0,
               "service_date": "2026-03-01", "provider_id": "PR1", "dx": "S72"}],
}


def main() -> None:
    init_db()
    with SessionLocal() as db:
        assess_and_store(db, CLAIM)                              # lifecycle LODGED, merits PENDING
        lc.transition(db, CID, "validate", H)                   # -> VALIDATED
        lc.transition(db, CID, "open_merits", H)                # -> MERITS
        mer.decide(db, CID, "accept", H, fault_pct=25)          # merits ACCEPTED (25%)
        lc.transition(db, CID, "accept_merits", H)              # -> QUANTUM
        s = si.create(db, CID, list_match=True, wpi=35)         # RAF 4 SUBMITTED
        si.transition(db, s.id, "accept", M)                    # -> RAF_ACCEPTED (opens GD)
        persist_offer(db, CID, {                                # offer ASSEMBLED (all heads)
            "loss_of_earnings": {"annual_losses": [200000, 500000]},
            "general_damages": {"proposed": 800000, "band_p25": 500000, "band_p75": 1000000},
        }, H)
        lc.transition(db, CID, "make_offer", H)                 # -> OFFER_MADE
        u = und.issue(db, CID, "SETTLEMENT", ["S72"], M)        # undertaking ISSUED
        und.transition(db, u.id, "activate", M)                 # -> ACTIVE
        inv = und.submit_invoice(db, u.id, 500.0, "S72", M)     # invoice RECEIVED
        und.adjudicate_invoice(db, inv.id, 460.0, M)            # -> ADJUDICATED (payable 460)
        lt = lit.create(db, CID, L)                             # litigation SUMMONS_SERVED
        lit.transition(db, lt.id, "plead", L)                   # -> PLEADINGS
        print(f"showcase {CID}: lifecycle=OFFER_MADE, merits=ACCEPTED(25%), RAF4=ACCEPTED, "
              f"offer ASSEMBLED, undertaking ACTIVE(+invoice), litigation=PLEADINGS")


if __name__ == "__main__":
    main()
