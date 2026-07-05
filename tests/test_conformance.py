"""Conformance: the modular `engine` package must reproduce the single-file oracle exactly.

`spec/rie_engine.py` is deterministic and side-effect-free, so it is the acceptance oracle. For
every scenario we run the same inputs through the oracle and through the package and assert the
determination records are identical. Any divergence fails here — the engine can never silently
drift from its spec.
"""
from __future__ import annotations

import engine as modular
import pytest
import spec.rie_engine as oracle
from scenarios import SCENARIOS


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_modular_matches_oracle(name):
    build = SCENARIOS[name]
    expected = oracle.process_claim(**build(oracle))
    actual = modular.process_claim(**build(modular))
    assert actual == expected, (
        f"\nscenario: {name}\n oracle:  {expected}\n modular: {actual}"
    )


def test_scenario_coverage():
    # guardrail: the suite must stay broad
    assert len(SCENARIOS) >= 40, f"only {len(SCENARIOS)} scenarios — expected the full matrix"
