"""The app must import from a cold interpreter, whichever module is loaded first.

The test suite imports the app once, in one order, so an import cycle between services can pass
every other test and still stop the server from starting. Each entry point is therefore imported
in its own fresh interpreter, against an in-memory database."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ENTRY_POINTS = ["server.main", "server.admin_service", "server.precision_service", "server.rates_service",
                "server.reference_data", "server.work_query", "server.payments_service",
                "server.provider_registry_service", "server.claims_query"]


@pytest.mark.parametrize("module", ENTRY_POINTS)
def test_module_imports_from_a_cold_interpreter(module):
    env = {**os.environ, "RIE_DATABASE_URL": "sqlite://", "RIE_ENV": "test"}
    r = subprocess.run([sys.executable, "-c", f"import {module}"], cwd=ROOT, env=env,
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-1500:]
