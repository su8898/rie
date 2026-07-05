"""COIDA→RAF crosswalk machinery + its wiring into build_refbook.

Hermetic. The key guarantees:
  - `apply_crosswalk` aliases additively and the engine then prices the alias;
  - it never overwrites a real reference rate, and skips missing targets;
  - PRODUCTION SAFETY: CONFIRMED-only by default, so drafting the crosswalk shifts no live price;
  - build_refbook actually calls it (a CONFIRMED entry flows through to a priced RefBook).
"""
from __future__ import annotations

import server.crosswalk as xw
from engine import RefBook, resolve


def _book(rpl):
    return RefBook(negotiated={}, rpl=rpl, raf2022={}, empirical={}, sep={}, non_benchmarkable=set())


def test_default_applies_confirmed_holds_back_proposed(monkeypatch):
    # MECHANISM (independent of the real confirmed set): default apply = CONFIRMED only; what_if
    # adds PROPOSED; NEEDS_SME/NO_RAF (raf=None) are never applied.
    monkeypatch.setattr(xw, "CROSSWALK", [
        xw.XW("111", "t", "d", "999", xw.CONFIRMED, "e"),
        xw.XW("222", "t", "d", "999", xw.PROPOSED, "e"),
        xw.XW("333", "t", "d", None, xw.NEEDS_SME, "e"),
    ])
    b = _book({"999": {"GP": 100.0}})
    assert {e.coida for e, _ in xw.apply_crosswalk(b)} == {"111"}               # CONFIRMED only
    assert resolve(b, "TARIFF", "111")[0] == 100.0 and resolve(b, "TARIFF", "222")[0] is None
    b2 = _book({"999": {"GP": 100.0}})
    assert {e.coida for e, _ in xw.apply_crosswalk(b2, what_if=True)} == {"111", "222"}  # + PROPOSED


def test_confirmed_mappings_are_the_signed_set():
    confirmed = {e.coida for e in xw.CROSSWALK if e.status == xw.CONFIRMED}
    assert confirmed == {"0186", "4805", "0190", "0146", "0614"}    # the 5 SME-signed mappings


def test_grounded_set_applies_and_the_engine_then_prices_it():
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
        assert (e.raf is None) == (e.status in (xw.NEEDS_SME, xw.NO_RAF))  # target iff CONFIRMED/PROPOSED
        assert e.evidence and e.corpus_desc


def test_build_refbook_applies_confirmed_crosswalk(monkeypatch):
    # end-to-end wiring: a CONFIRMED equivalence must flow through build_refbook into pricing.
    from server import models
    from server.db import Base, SessionLocal, engine as db_engine
    from server.reference_data import build_refbook

    Base.metadata.create_all(db_engine)
    with SessionLocal() as db:
        db.merge(models.RefRpl(code="88888", discipline="GP", rate=123.45))    # a RAF target
        db.commit()
        confirmed = xw.XW("77777", "test", "unit", "88888", xw.CONFIRMED, "unit-test equivalence")
        monkeypatch.setattr(xw, "CROSSWALK", [confirmed])
        book = build_refbook(db, nappi_codes=set())

    rate, src, status = resolve(book, "TARIFF", "77777")     # aliased onto 88888 by build_refbook
    assert rate == 123.45 and status.name == "ACCEPTED"
