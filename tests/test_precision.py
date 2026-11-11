"""Precision / recall governance (§11) — Wilson intervals, substantiation, promotion, recall QA."""
from __future__ import annotations

import test_api  # noqa: F401  (sets RIE_DATABASE_URL + imports the app + seeds)
from fastapi.testclient import TestClient
from server import models, precision_service as svc
from server.db import SessionLocal
from server.main import app

client = TestClient(app)


def _login(user="handler"):
    assert client.post("/api/auth/login", json={"username": user, "password": user}).status_code == 200


def _seed(signal, n_adverse, n_benign, band="GREEN", tag="P"):
    """n_adverse + n_benign claims that fired `signal`, each labelled by a closed case."""
    with SessionLocal() as db:
        for i in range(n_adverse + n_benign):
            cid = f"{tag}_{signal}_{i}"
            db.add(models.Determination(
                claim_id=cid, accident_id="A", accident_action="CREATED", band=band, score=0,
                disposition="CLEAN", validated=True, convergence=0.0, medical_payable=0.0,
                net_payable=0.0, eligible_to_pay=True, reasons=[signal], shadow_signals=[],
                holds=[], engine_version="t", ruleset_effective="", reference_edition=""))
            db.add(models.Case(claim_id=cid, lane="BLOCK", status="CLOSED", priority=3, reason="t",
                               verdict="CONFIRMED_FRAUD" if i < n_adverse else "CLEARED",
                               opened_by="investigator"))
        db.commit()


# ── Wilson score interval (pure) ──────────────────────────────────────────────
def test_wilson_empty_is_none():
    w = svc.wilson(0, 0)
    assert w["point"] is None and w["lower"] is None and w["n"] == 0


def test_wilson_perfect_six_clears_the_floor():
    w = svc.wilson(6, 6)
    assert w["point"] == 1.0 and w["lower"] >= svc.SCORED_FLOOR   # 6/6 -> ~0.61


def test_wilson_perfect_five_below_the_floor():
    assert svc.wilson(5, 5)["lower"] < svc.SCORED_FLOOR           # 5/5 -> ~0.57 (small-n self-guard)


def test_wilson_half_brackets_the_point():
    w = svc.wilson(5, 10)
    assert w["point"] == 0.5 and 0 < w["lower"] < 0.5 < w["upper"] < 1


# ── promotion-lifecycle logic (pure) ──────────────────────────────────────────
def test_recommend_grounded_is_always_scored():
    from engine.reasons import R
    assert svc._recommend("SCORED", R["PRESCRIBED_LODGEMENT"], svc.wilson(0, 0)) == "SCORED"


def test_recommend_insufficient_labels_holds_current():
    from engine.reasons import R
    assert svc._recommend("SHADOW", R["DX_ACCIDENT_MISMATCH"], svc.wilson(2, 3)) == "SHADOW"


def test_recommend_promotes_above_floor_advises_below():
    from engine.reasons import R
    meta = R["DX_ACCIDENT_MISMATCH"]
    assert svc._recommend("ADVISORY", meta, svc.wilson(6, 6)) == "SCORED"    # >= 60% Wilson-lower
    assert svc._recommend("SCORED", meta, svc.wilson(3, 6)) == "ADVISORY"    # below floor -> demote


# ── precision / labels / recall (integration) ─────────────────────────────────
def test_precision_by_signal_measures_substantiation():
    _seed("ZZ_HEUR_HI", 6, 0)                                     # 6/6 substantiated
    with SessionLocal() as db:
        r = {x["signal"]: x for x in svc.precision_by_signal(db)}["ZZ_HEUR_HI"]
    assert r["labeled"] == 6 and r["substantiated"] == 6 and r["substantiation"] == 1.0
    assert r["wilson_lower"] >= svc.SCORED_FLOOR and r["recommended_mode"] == "SCORED"


def test_precision_below_floor_recommends_advisory():
    _seed("ZZ_HEUR_LO", 3, 3)                                     # 3/6 substantiated
    with SessionLocal() as db:
        r = {x["signal"]: x for x in svc.precision_by_signal(db)}["ZZ_HEUR_LO"]
    assert r["labeled"] == 6 and r["substantiation"] == 0.5 and r["recommended_mode"] == "ADVISORY"


def test_labels_export_and_recall_estimate():
    _seed("ZZ_MISS", 2, 0, band="GREEN")                         # 2 GREEN claims later found adverse
    with SessionLocal() as db:
        lbls = svc.labels_export(db)
        rec = svc.recall_estimate(db)
    assert any(x["label"] == "ADVERSE" and x["verdict"] == "CONFIRMED_FRAUD" for x in lbls)
    assert rec["reviewed"] >= 2 and rec["misses"] >= 2 and 0 <= rec["recall_floor"] <= 1


# ── API ───────────────────────────────────────────────────────────────────────
def test_governance_endpoints_require_auth():
    client.post("/api/auth/logout")
    for path in ("/api/governance/precision", "/api/governance/recall", "/api/governance/labels"):
        assert client.get(path).status_code == 401


def test_governance_api_precision_promotions_labels_csv_recall():
    _seed("ZZ_API", 6, 0)
    _login()
    p = {r["signal"]: r for r in client.get("/api/governance/precision").json()}
    assert p["ZZ_API"]["recommended_mode"] == "SCORED"
    assert isinstance(client.get("/api/governance/promotions").json(), list)
    csv_resp = client.get("/api/governance/labels.csv")
    assert csv_resp.status_code == 200 and csv_resp.text.startswith("claim_id,verdict,label,lane,case_id")
    samp = client.get("/api/governance/recall/sample", params={"n": 5}).json()
    assert samp["sample_size"] <= 5 and "claims" in samp


# ── QA-draw workflow (recall close-the-loop) ──────────────────────────────────
def test_draw_recall_qa_opens_review_cases_idempotently():
    from sqlalchemy import select
    _seed("ZZ_DRAW", 0, 3, band="GREEN")                          # fresh GREEN pool, no REVIEW cases
    user = {"username": "qa", "role": "ADMIN"}
    with SessionLocal() as db:
        first = svc.draw_recall_qa(db, user, n=5)
        assert first["drawn"] >= 1                                # opened blind-QA REVIEW cases
        opened = list(db.scalars(select(models.Case).where(
            models.Case.lane == "REVIEW", models.Case.status == "OPEN",
            models.Case.reason.like("Blind QA%"))))
        assert len(opened) >= first["drawn"]
        second = svc.draw_recall_qa(db, user, n=5)               # same deterministic sample
        assert second["drawn"] == 0 and second["skipped"] == second["sampled"]


def test_draw_recall_qa_api():
    _login()
    r = client.post("/api/governance/recall/draw", params={"n": 4}).json()
    assert set(r) == {"drawn", "sampled", "skipped"} and r["drawn"] + r["skipped"] == r["sampled"]
    client.post("/api/auth/logout")
    assert client.post("/api/governance/recall/draw").status_code == 401


def test_an_applied_mode_change_is_not_suggested_again():
    """Governance must read the mode in force (the administrator's override), not the default."""
    from server import admin_service
    from server.db import SessionLocal
    with SessionLocal() as db:
        rows = svc.precision_by_signal(db)
        code = next((r["signal"] for r in rows if r["maturity"] != "GROUNDED"), None)
        if code is None:
            return
        before = next(r for r in rows if r["signal"] == code)
        other = "ADVISORY" if before["current_mode"] != "ADVISORY" else "SHADOW"
        admin = {"username": "admin", "role": "ADMIN"}
        try:
            admin_service.set_signal_mode(db, admin, code, other, note="test")
            after = next(r for r in svc.precision_by_signal(db) if r["signal"] == code)
            assert after["current_mode"] == other
            if after["recommended_mode"] == other:
                assert all(p["signal"] != code for p in svc.promotions(db))
        finally:
            admin_service.clear_signal_mode(db, admin, code)
        assert next(r for r in svc.precision_by_signal(db) if r["signal"] == code)["current_mode"] == before["current_mode"]
