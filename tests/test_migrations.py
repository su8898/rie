"""Alembic migrations — `alembic upgrade head` builds a schema matching the ORM, reversibly.

Run in an isolated subprocess (a fresh RIE_DATABASE_URL) so it never touches the suite's shared
DB. Skips if Alembic isn't installed.
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys

import pytest

pytest.importorskip("alembic")

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _alembic(db_url: str, *args: str):
    env = {**os.environ, "RIE_DATABASE_URL": db_url}
    return subprocess.run([sys.executable, "-m", "alembic", *args], cwd=REPO, env=env,
                          capture_output=True, text=True, timeout=120)


def _tables(db) -> set[str]:
    con = sqlite3.connect(db)
    try:
        return {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        con.close()


def test_upgrade_head_matches_orm_and_is_reversible(tmp_path):
    db = tmp_path / "mig.db"
    url = f"sqlite:///{db}"

    up = _alembic(url, "upgrade", "head")
    assert up.returncode == 0, up.stderr

    # parity: `alembic check` exits 0 only when the migration matches the ORM metadata exactly
    chk = _alembic(url, "check")
    assert chk.returncode == 0, f"migration drifted from the ORM:\n{chk.stdout}\n{chk.stderr}"

    # every ORM table exists in the migrated DB
    from server import models  # noqa: F401  (import populates Base.metadata)
    from server.db import Base
    tables = _tables(db)
    assert set(Base.metadata.tables) <= tables and "alembic_version" in tables

    # reversible: downgrade base drops everything but the version table
    down = _alembic(url, "downgrade", "base")
    assert down.returncode == 0, down.stderr
    assert _tables(db) == {"alembic_version"}
