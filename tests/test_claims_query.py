"""The claims worklist and claim record as the operator console reads them."""
from __future__ import annotations

import test_api  # noqa: F401  (sets RIE_DATABASE_URL + imports the app first)
from fastapi.testclient import TestClient

from server.main import app

c = TestClient(app)


def _login(user="handler"):
    assert c.post("/api/auth/login", json={"username": user, "password": user}).status_code == 200


def _claim(cid, provider, amount, lodged="2026-03-01", ctype="SUPPLIER", **kw):
    docs = ({"RAF2": True, "OAR": True, "INVOICES": True, "BANK": True} if ctype == "SUPPLIER"
            else {"RAF1": True, "OAR": True, "ID": True, "BANK": True})
    return {"claim_id": cid, "claim_type": ctype, "party_token": f"P_{cid}",
            "accident_date": "2026-02-01", "lodged_on": lodged, "case_number_raw": "CAS 8600/02/2026",
            "today": "2026-07-05", "payee_verified": True, "documents": docs,
            "lines": [{"kind": "TARIFF", "code": "0190", "qty": 1, "amount": amount,
                       "service_date": "2026-03-01", "provider_id": provider, "dx": "S72"}], **kw}


def _seed():
    _login()
    for body in (_claim("R_CQ_1", "PR_CQ_A", 500.0, lodged="2026-03-01"),
                 _claim("R_CQ_2", "PR_CQ_A", 800.0, lodged="2026-03-05"),
                 _claim("R_CQ_3", "PR_CQ_B", 300.0, lodged="2026-03-09", ctype="PERSONAL")):
        r = c.post("/api/claims", json=body)
        assert r.status_code in (200, 409), r.text


def _list(**params):
    r = c.get("/api/claims", params={"q": "R_CQ_", **params})
    assert r.status_code == 200, r.text
    return r.json(), int(r.headers["X-Total-Count"])


def test_worklist_rows_carry_the_claim_and_its_billing():
    _seed()
    rows, total = _list()
    assert total == 3 and [r["claim_id"] for r in rows] == ["R_CQ_3", "R_CQ_2", "R_CQ_1"]   # newest first
    two = rows[1]
    assert (two["claim_type"], two["lodged_on"], two["accident_date"]) == ("SUPPLIER", "2026-03-05", "2026-02-01")
    assert (two["billed"], two["net_payable"], two["providers"]) == (800.0, 500.0, ["PR_CQ_A"])
    assert two["party_token"] == "P_R_CQ_2" and two["disposition"] == "ADJUSTED"


def test_worklist_filters():
    _seed()
    assert [r["claim_id"] for r in _list(claim_type="PERSONAL")[0]] == ["R_CQ_3"]
    assert [r["claim_id"] for r in _list(provider_id="pr_cq_a")[0]] == ["R_CQ_2", "R_CQ_1"]
    assert [r["claim_id"] for r in _list(lodged_from="2026-03-05", lodged_to="2026-03-08")[0]] == ["R_CQ_2"]
    assert {r["claim_id"] for r in _list(eligible=True)[0]} == {"R_CQ_1", "R_CQ_2"}
    assert [r["claim_id"] for r in _list(eligible=False)[0]] == ["R_CQ_3"]          # merits pending
    assert [r["claim_id"] for r in _list(disposition="ADJUSTED")[0]] == ["R_CQ_2"]
    assert c.get("/api/claims", params={"q": "P_R_CQ_3"}).json()[0]["claim_id"] == "R_CQ_3"   # by claimant token
    assert _list(provider_id="  ")[1] == 3


def test_worklist_sorting_and_paging():
    _seed()
    assert [r["claim_id"] for r in _list(sort="payable", direction="asc")[0]] == ["R_CQ_3", "R_CQ_2", "R_CQ_1"]
    assert [r["claim_id"] for r in _list(sort="lodged", direction="asc")[0]] == ["R_CQ_1", "R_CQ_2", "R_CQ_3"]
    assert [r["claim_id"] for r in _list(sort="claim", direction="desc")[0]] == ["R_CQ_3", "R_CQ_2", "R_CQ_1"]
    page, total = _list(sort="claim", direction="asc", limit=1, offset=1)
    assert total == 3 and [r["claim_id"] for r in page] == ["R_CQ_2"]
    assert c.get("/api/claims", params={"sort": "nonsense"}).status_code == 422
    assert c.get("/api/claims", params={"direction": "sideways"}).status_code == 422
    assert _list(sort="score")[1] == 3


def test_claim_record_shows_each_line_the_history_and_the_payment():
    _seed()
    d = c.get("/api/claims/R_CQ_2").json()
    assert d["billed"] == 800.0 and d["determination"]["net_payable"] == 500.0
    assert d["lines"] == [{
        "id": d["lines"][0]["id"], "provider_id": "PR_CQ_A", "kind": "TARIFF", "code": "0190",
        "service_date": "2026-03-01", "billed": 800.0, "reference": 500.0, "payable": 500.0,
        "reduced": 300.0, "source": "RPL", "legal_status": "ACCEPTED", "needs_review": False,
        "reasons": ["BILLED_OVER_REFERENCE"]}]
    assert len(d["history"]) == 1 and d["history"][0]["disposition"] == "ADJUSTED"
    assert d["payment"] == {"status": "NOT_QUEUED", "amount": None, "remittances": [], "batch_id": None}
    assert d["practices"] == [{"provider_id": "PR_CQ_A", "known": False, "may_bill": True}]

    _login("admin")
    assert c.post("/api/claims/R_CQ_2/rescore").status_code == 200
    history = c.get("/api/claims/R_CQ_2").json()["history"]
    assert len(history) == 2 and history[0]["id"] > history[1]["id"]           # newest first
    assert c.get("/api/claims/R_CQ_NOPE").status_code == 404
