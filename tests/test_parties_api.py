"""Party-intelligence endpoints — provider cohorts/scoring, attorneys, claimant recurrence,
fairness, risk sweep — over the corpus."""
from __future__ import annotations

import test_api  # noqa: F401  (sets RIE_DATABASE_URL + imports the app first)
from fastapi.testclient import TestClient
from server.main import app

client = TestClient(app)


def _login(user="investigator"):
    assert client.post("/api/auth/login", json={"username": user, "password": user}).status_code == 200


def _supplier(cid, party, cas, provider, amount=500.0, dx="S72", dx_regions=None, attorney=None,
              accident_date="2026-02-01", lodged_on="2026-03-01"):
    p = {"claim_id": cid, "claim_type": "SUPPLIER", "party_token": party,
         "accident_date": accident_date, "lodged_on": lodged_on, "case_number_raw": cas,
         "today": "2026-07-05", "payee_verified": True,
         "documents": {"RAF2": True, "OAR": True, "INVOICES": True, "BANK": True},
         "lines": [{"kind": "TARIFF", "code": "0190", "qty": 1, "amount": amount,
                    "service_date": "2026-03-01", "provider_id": provider, "dx": dx}]}
    if dx_regions:
        p["accident_dx_regions"] = dx_regions
    if attorney:
        p["attorney"] = attorney
    return p


def _seed():
    _login("handler")
    n = 0
    for i in range(5):                                             # PR_HI: 2 of 5 flagged (dx mismatch)
        flagged = i < 2
        client.post("/api/claims", json=_supplier(
            f"R_piH{i}", f"P_piH{i}", f"CAS 951{i}/02/2026", "PR_HI",
            dx="K35" if flagged else "S72", dx_regions=["S72"] if flagged else None,
            attorney="Dubious & Co"))
        n += 1
    for i in range(5):                                             # PR_LO: clean
        client.post("/api/claims", json=_supplier(
            f"R_piL{i}", f"P_piL{i}", f"CAS 952{i}/02/2026", "PR_LO", attorney="Honest LLP"))
    for i in range(5):                                             # PR_SPEC: high-value -> SPECIALIST
        client.post("/api/claims", json=_supplier(
            f"R_piS{i}", f"P_piS{i}", f"CAS 953{i}/02/2026", "PR_SPEC", amount=1000.0))
    # a recurring claimant across two DISTINCT accidents (different dates so they don't merge)
    client.post("/api/claims", json=_supplier("R_rec1", "P_REC", "CAS 9540/02/2026", "PR_LO"))
    client.post("/api/claims", json=_supplier("R_rec2", "P_REC", "CAS 9541/06/2024", "PR_LO",
                                              accident_date="2024-06-15", lodged_on="2024-07-01"))


def test_provider_intelligence():
    _seed()
    _login("investigator")
    provs = {p["provider_id"]: p for p in client.get("/api/parties/providers").json()}
    assert "PR_HI" in provs and "PR_LO" in provs and "PR_SPEC" in provs
    assert provs["PR_HI"]["n_claims"] == 5
    assert provs["PR_HI"]["flag_rate"] == 40.0                     # 2 of 5 dx-mismatch
    assert provs["PR_LO"]["flag_rate"] == 0.0
    assert provs["PR_HI"]["score"] > provs["PR_LO"]["score"]       # flagged provider ranks higher
    assert provs["PR_SPEC"]["archetype"] == "SPECIALIST"           # avg value >= 800
    assert provs["PR_LO"]["archetype"] == "GENERAL"


def test_attorney_intelligence():
    _seed()
    _login("investigator")
    atts = {a["attorney"]: a for a in client.get("/api/parties/attorneys").json()}
    assert "Dubious & Co" in atts and "Honest LLP" in atts
    assert atts["Dubious & Co"]["n_claims"] == 5
    assert atts["Dubious & Co"]["claim_type_mix"] == {"SUPPLIER": 5}


def test_claimant_recurrence():
    _seed()
    _login("investigator")
    rec = {c["party_token"]: c for c in client.get("/api/parties/claimants").json()}
    assert "P_REC" in rec and rec["P_REC"]["n_accidents"] == 2
    assert "P_piH0" not in rec                                     # single-accident claimants excluded


def test_fairness_report():
    _seed()
    _login("investigator")
    f = client.get("/api/parties/fairness").json()
    assert "four_fifths_ratio" in f and isinstance(f["pass"], bool)
    cohorts = {r["cohort"] for r in f["by_cohort"]}
    assert "GENERAL" in cohorts and "SPECIALIST" in cohorts


def test_risk_sweep():
    _seed()
    _login("investigator")
    sweep = client.get("/api/parties/risk-sweep", params={"threshold": 0}).json()
    assert sweep["n"] >= 1
    assert any(x["type"] == "provider" and x["id"] == "PR_HI" for x in sweep["flagged"])
    assert sweep["flagged"] == sorted(sweep["flagged"], key=lambda r: r["score"], reverse=True)
