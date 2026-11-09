"""Seed a couple of payment batches (one OPEN with instructions, one PAID) from the eligible
queue — for demos/screenshots of the payments page. Run after seed_demo."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import payments_service as pay  # noqa: E402
from server.db import SessionLocal  # noqa: E402
from server.seed import init_db  # noqa: E402

H = {"username": "handler", "role": "HANDLER"}
A = {"username": "admin", "role": "ADMIN"}
T = {"username": "treasury", "role": "ADMIN"}      # payer — must differ from assembler + approver


def main() -> None:
    init_db()
    with SessionLocal() as db:
        q = pay.queue(db)
        if len(q) < 3:
            print(f"only {len(q)} eligible claims — run `python3 db/seed_demo.py` first")
            return
        b1 = pay.create_batch(db, H, note="Weekly supplier run")          # OPEN + 2 instructions
        pay.add_instruction(db, b1.id, q[0]["claim_id"], "SUPPLIER", None, H)
        pay.add_instruction(db, b1.id, q[1]["claim_id"], "SUPPLIER", None, H)
        b2 = pay.create_batch(db, H, note="EMS run")                      # assembled -> approved -> paid
        pay.add_instruction(db, b2.id, q[2]["claim_id"], "SUPPLIER", None, H)
        pay.approve(db, b2.id, A)
        pay.pay(db, b2.id, T)
        print(f"payments seeded: batch {b1.id} OPEN (2 instr, "
              f"R{pay._total(db, b1.id):,.2f}), batch {b2.id} PAID (R{pay._total(db, b2.id):,.2f})")


if __name__ == "__main__":
    main()
