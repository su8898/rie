"""Deploy-time initialisation — the one-shot `init` service in docker-compose.prod.yml.

Runs before the API on EVERY deploy, so every step must be safe to repeat:

  1. bring the schema to head (Alembic) — a new release's migrations are applied here;
  2. load reference.db — ONLY when the reference tables are empty (first boot). The full loader
     deletes and re-inserts the tariff, NAPPI and ICD-10 tables, which would discard whatever an
     administrator has since maintained through the app, so a redeploy must not repeat it;
  3. seed users + statutory config (each step only fills an empty table).

To reload the reference snapshot deliberately, run the init service once with
RIE_RELOAD_REFERENCE=1 (see README, "Production deployment").
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import func, select  # noqa: E402

from db.load_reference import REFERENCE_DB, ensure_schema, load  # noqa: E402
from server import models  # noqa: E402
from server.db import SessionLocal  # noqa: E402
from server.seed import seed  # noqa: E402


def _count(db, model) -> int:
    return db.scalar(select(func.count()).select_from(model)) or 0


def main() -> None:
    t0 = time.time()
    ensure_schema()
    print("schema at head", flush=True)
    force = os.environ.get("RIE_RELOAD_REFERENCE", "") == "1"
    with SessionLocal() as db:
        have = {"tariffs": _count(db, models.RefRpl), "nappi": _count(db, models.RefNappiSep)}
        if force or not any(have.values()):
            if not os.path.isfile(REFERENCE_DB):
                sys.exit(f"reference tables are empty and {REFERENCE_DB} is missing — copy "
                         f"reference.db next to docker-compose.prod.yml and run the deploy again")
            print(f"loading reference data from {REFERENCE_DB} ...", flush=True)
            print(f"loaded: {load(db)}", flush=True)
        else:
            print(f"reference data already present {have} — left untouched", flush=True)
        seed(db)
    print(f"init done in {time.time() - t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
