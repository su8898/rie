"""Offer-builder endpoint — heads of damage (Sweatman cap, GD gating) end-to-end over HTTP."""
from __future__ import annotations

import test_api  # noqa: F401  (sets RIE_DATABASE_URL + imports the app first)
from fastapi.testclient import TestClient
from server.main import app

client = TestClient(app)

BASE = {
    "claim_id": "R_off1", "claim_type": "PERSONAL", "party_token": "P_off1",
    "accident_date": "2026-02-01", "lodged_on": "2026-03-01",
    "case_number_raw": "CAS 700/02/2026", "today": "2026-07-05",
    "documents": {"RAF1": True, "OAR": True, "ID": True, "BANK": True},
    "payee_verified": True, "merits_accepted": True, "fault_pct": 0,
    "lines": [{"kind": "TARIFF", "code": "0190", "qty": 1, "amount": 500.0,
               "service_date": "2026-03-01", "provider_id": "PR1", "dx": "S72"}],
}


def _login(user="handler"):
    assert client.post("/api/auth/login", json={"username": user, "password": user}).status_code == 200


def test_offer_all_heads():
    _login()
    p = {**BASE, "si_accepted": True, "heads_input": {
        "loss_of_earnings": {"annual_losses": [200000, 500000]},
        "general_damages": {"proposed": 800000, "band_p25": 500000, "band_p75": 1000000}}}
    r = client.post("/api/offer", json=p).json()
    assert r["heads"]["past_medical"] == 500.0
    # cap@accident-date (2026-02-01) = 378581; y1 min(200000,cap)=200000, y2 min(500000,cap)=378581
    assert r["heads"]["loss_of_earnings"]["total"] == 578581.0
    assert len(r["heads"]["loss_of_earnings"]["worksheet"]) == 2
    assert r["heads"]["general_damages"]["amount"] == 800000.0          # within band, fault 0
    assert r["heads"]["general_damages"]["reasons"] == []
    assert r["offer_total"] == round(500.0 + 578581.0 + 800000.0, 2)
    assert r["gated_by"] == []


def test_offer_loss_of_support_and_funeral_heads():
    # a deceased-claimant offer: dependants' loss of support (§5c) + funeral (§5e)
    _login()
    p = {**BASE, "claim_id": "R_off4", "party_token": "P_off4", "heads_input": {
        "loss_of_support": {"annual_losses": [200000, 500000]},
        "funeral": {"necessary_costs": 40000, "non_necessary": 6000}}}
    r = client.post("/api/offer", json=p).json()
    # loss of support shares the Sweatman cap engine: cap@accident-date (2026-02-01) = 378581
    assert r["heads"]["loss_of_support"]["total"] == 578581.0       # 200000 + min(500000,378581)
    assert len(r["heads"]["loss_of_support"]["worksheet"]) == 2
    assert r["heads"]["funeral"]["amount"] == 40000.0              # fault 0 -> full necessary costs
    assert r["heads"]["funeral"]["reasons"] == ["FUNERAL_SCOPE"]   # non-necessary present -> soft flag
    assert r["offer_total"] == round(500.0 + 578581.0 + 40000.0, 2)
    assert r["gated_by"] == []


def test_offer_gd_band_computed_from_awards_store():
    # §5d — pass an injury class + tier; the band is COMPUTED (CPI-adjusted p25–p75), not hand-fed
    _login()
    p = {**BASE, "claim_id": "R_off6", "party_token": "P_off6", "si_accepted": True,
         "heads_input": {"general_damages": {
             "proposed": 2800000, "injury_class": "TBI", "severity_tier": "SEVERE"}}}
    gd = client.post("/api/offer", json=p).json()["heads"]["general_damages"]
    assert gd["authorities"]["n"] == 6 and gd["authorities"]["robust"] is True
    assert gd["band_p25"] < 2800000 < gd["band_p75"]    # proposed within the computed band
    assert gd["amount"] == 2800000.0 and gd["reasons"] == []   # guidance only, fault 0 -> full


def test_offer_gd_gated_without_si():
    _login()
    p = {**BASE, "claim_id": "R_off2", "party_token": "P_off2", "si_accepted": False,
         "heads_input": {"general_damages": {"proposed": 800000, "band_p25": 500000, "band_p75": 1000000}}}
    r = client.post("/api/offer", json=p).json()
    assert r["heads"]["general_damages"]["amount"] == 0.0
    assert "GENERAL_DAMAGES_NO_SI" in r["heads"]["general_damages"]["reasons"]


def test_offer_held_without_merits():
    _login()
    p = {**BASE, "claim_id": "R_off3", "party_token": "P_off3", "merits_accepted": None}
    r = client.post("/api/offer", json=p).json()
    assert r["offer_total"] == 0.0
    assert "held_for_merits" in r["gated_by"]


def test_offer_rbac():
    client.post("/api/auth/logout")
    _login("investigator")
    assert client.post("/api/offer", json=BASE).status_code == 403
