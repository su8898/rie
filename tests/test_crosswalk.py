"""COIDA→RAF crosswalk machinery — additive aliasing, and the production-safety invariant.

Hermetic: builds tiny in-memory RefBooks, no external snapshots. The key guarantee tested is that
`apply_crosswalk` changes nothing until an entry is SME-CONFIRMED (default applies CONFIRMED only),
so drafting the stub never shifts production pricing.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "db"))

import crosswalk as xw  # noqa: E402
from engine import RefBook, resolve  # noqa: E402


def _book(rpl):
    return RefBook(negotiated={}, rpl=rpl, raf2022={}, empirical={}, sep={}, non_benchmarkable=set())


def test_confirmed_only_default_is_a_noop():
    # PRODUCTION SAFETY: no entry is CONFIRMED yet, so the default apply must not touch pricing.
    book = _book({"10190": {"GP": 587.24}})
    before = {k: dict(v) for k, v in book.rpl.items()}
    assert xw.apply_crosswalk(book) == []
    assert book.rpl == before


def test_what_if_applies_proposed_and_the_engine_then_prices_it():
    book = _book({"10190": {"GP": 587.24}, "147": {"GP": 489.16}, "4804": {"GP": 1048.20},
                  "2712": {"GP": 580.0}, "909": {"GP": 5073.29}})
    applied = xw.apply_crosswalk(book, what_if=True)
    assert {e.coida for e, _ in applied} >= {"0190", "0146", "4805", "0186", "0614"}
    # the aliased COIDA code now resolves to its RAF target's rate, ACCEPTED (drives pay-min)
    rate, src, status = resolve(book, "TARIFF", "0190")     # -> normalised "190" -> alias of 10190
    assert rate == 587.24 and status.name == "ACCEPTED"


def test_never_overwrites_an_existing_reference_rate():
    book = _book({"10190": {"GP": 587.24}, "190": {"GP": 999.0}})   # "0190" normalises to a covered code
    xw.apply_crosswalk(book, what_if=True)
    assert book.rpl["190"] == {"GP": 999.0}                 # real reference wins, alias skipped


def test_missing_target_is_skipped():
    assert xw.apply_crosswalk(_book({}), what_if=True) == []  # no RAF targets loaded -> nothing applied


def test_every_entry_is_well_formed():
    for e in xw.CROSSWALK:
        assert e.status in (xw.CONFIRMED, xw.PROPOSED, xw.NEEDS_SME, xw.NO_RAF)
        assert (e.raf is None) == (e.status in (xw.NEEDS_SME, xw.NO_RAF))  # target iff (C)ONFIRMED/PROPOSED
        assert e.evidence and e.corpus_desc
