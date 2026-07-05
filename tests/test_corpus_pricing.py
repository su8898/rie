"""Integration: the engine priced against a REAL claims corpus (when the snapshots are present).

This drives `db/corpus_test.py` — which prices ~52k real SA medical claims against the seeded
real RAF reference — in an isolated subprocess, and asserts the engine (a) resolves/reprices real
codes and (b) stays byte-for-byte conformant with the oracle on real claims.

Both inputs are local, gitignored snapshots (reference.db seeded into rie.db, and the external
claims.db), so this test SKIPS cleanly on any machine that doesn't have them — CI stays hermetic.
Run locally with the snapshots in place and it exercises the whole pricing spine on actual data.
"""
from __future__ import annotations

import os
import subprocess
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RIE_DB = os.path.join(REPO, "rie.db")
CORPUS_DB = os.environ.get("RIE_CORPUS_DB", os.path.expanduser("~/Desktop/old_cie_data/claims.db"))


def _reference_seeded() -> bool:
    if not os.path.isfile(RIE_DB):
        return False
    import sqlite3
    con = sqlite3.connect(RIE_DB)
    try:
        n = con.execute("SELECT count(*) FROM ref_rpl").fetchone()[0]
        return n > 0
    except sqlite3.Error:
        return False
    finally:
        con.close()


pytestmark = pytest.mark.skipif(
    not os.path.isfile(CORPUS_DB) or not _reference_seeded(),
    reason="real corpus (claims.db) and/or seeded reference (rie.db) not present on this machine",
)


def _run(limit: str):
    env = {**os.environ, "RIE_DATABASE_URL": f"sqlite:///{RIE_DB}",
           "RIE_CORPUS_DB": CORPUS_DB, "RIE_CORPUS_LIMIT": limit}
    return subprocess.run([sys.executable, "db/corpus_test.py"], cwd=REPO, env=env,
                          capture_output=True, text=True, timeout=180)


def test_engine_prices_real_corpus_and_stays_conformant():
    out = _run("2000")
    assert out.returncode == 0, out.stderr
    o = out.stdout
    # the engine actually priced real data ...
    assert "REFERENCE COVERAGE" in o and "PRICING" in o
    assert "repricing leakage" in o
    assert "BILLED_OVER_REFERENCE" in o                 # real over-reference billing was caught
    # ... and it is byte-for-byte the executable spec on real claims
    assert "byte-for-byte conformance holds on real data" in o
    assert "MISMATCH" not in o
