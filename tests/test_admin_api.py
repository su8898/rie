"""Admin module (SPECIFICATION §6) — users, statutory config, reference tiers, signal-mode
overrides, CUD audit log. ADMIN-only; overrides feed the engine live (§11)."""
from __future__ import annotations

import test_api  # noqa: F401  (sets RIE_DATABASE_URL + imports the app + seeds)
from fastapi.testclient import TestClient
from server.main import app

client = TestClient(app)


def _login(user="admin"):
    assert client.post("/api/auth/login", json={"username": user, "password": user}).status_code == 200


def test_admin_requires_admin_role():
    _login("handler")
    assert client.get("/api/admin/users").status_code == 403
    assert client.post("/api/admin/signal-modes", json={"code": "X", "mode": "SHADOW"}).status_code == 403


def test_user_management_and_guards():
    _login("admin")
    r = client.post("/api/admin/users",
                    json={"username": "clerk1", "role": "HANDLER", "password": "pw"}).json()
    assert r["username"] == "clerk1" and r["role"] == "HANDLER"
    assert any(u["username"] == "clerk1" for u in client.get("/api/admin/users").json())
    assert client.post("/api/auth/login", json={"username": "clerk1", "password": "pw"}).status_code == 200
    _login("admin")
    assert client.post("/api/admin/users/clerk1/role", json={"role": "LEGAL"}).json()["role"] == "LEGAL"
    assert client.post("/api/admin/users/clerk1/active", json={"active": False}).json()["active"] is False
    assert client.post("/api/admin/users",
                       json={"username": "clerk1", "role": "HANDLER", "password": "x"}).status_code == 400
    assert client.post("/api/admin/users",
                       json={"username": "z", "role": "KING", "password": "x"}).status_code == 400


def test_cannot_deactivate_self():
    _login("admin")
    assert client.post("/api/admin/users/admin/active", json={"active": False}).status_code == 400


def test_caps_preauth_negotiated():
    _login("admin")
    client.post("/api/admin/caps", json={"effective_from": "2027-01-31", "annual_cap": 400000})
    assert any(c["effective_from"] == "2027-01-31" for c in client.get("/api/admin/caps").json())
    client.post("/api/admin/preauth", json={"code": "0600"})
    assert "0600" in client.get("/api/admin/preauth").json()
    client.delete("/api/admin/preauth/0600")
    assert "0600" not in client.get("/api/admin/preauth").json()
    client.post("/api/admin/negotiated", json={"kind": "TARIFF", "code": "9999", "rate": 123.0})
    assert any(n["code"] == "9999" and n["rate"] == 123.0
               for n in client.get("/api/admin/negotiated").json())
    # delete cap + negotiated (reference data is fully CRUD-able)
    client.delete("/api/admin/caps/2027-01-31")
    assert not any(c["effective_from"] == "2027-01-31" for c in client.get("/api/admin/caps").json())
    client.delete("/api/admin/negotiated/TARIFF/9999")
    assert not any(n["code"] == "9999" for n in client.get("/api/admin/negotiated").json())


def test_signal_modes_list_and_override_guards():
    _login("admin")
    modes = {m["signal"]: m for m in client.get("/api/admin/signal-modes").json()}
    assert modes["RING_PARTIES"]["default_mode"] == "SHADOW" and modes["RING_PARTIES"]["overridable"] is True
    assert modes["PRESCRIBED_LODGEMENT"]["overridable"] is False           # Grounded, law-cited
    assert client.post("/api/admin/signal-modes",
                       json={"code": "PRESCRIBED_LODGEMENT", "mode": "SHADOW"}).status_code == 400
    assert client.post("/api/admin/signal-modes",
                       json={"code": "RING_PARTIES", "mode": "NOPE"}).status_code == 400
    assert client.post("/api/admin/signal-modes",
                       json={"code": "NOSUCH", "mode": "SHADOW"}).status_code == 400


_DXM = {"claim_type": "SUPPLIER", "party_token": "P_ovr", "accident_date": "2026-02-01",
        "lodged_on": "2026-03-01", "case_number_raw": "CAS 8/02/2026", "today": "2026-07-05",
        "documents": {"RAF2": True, "OAR": True, "INVOICES": True, "BANK": True},
        "payee_verified": True, "accident_dx_regions": ["S72"],
        "lines": [{"kind": "TARIFF", "code": "0190", "qty": 1, "amount": 500.0,
                   "service_date": "2026-03-01", "provider_id": "PR1", "dx": "K35"}]}   # dx mismatch


def test_signal_mode_override_changes_live_scoring_and_is_audited():
    _login("handler")
    r = client.post("/api/claims", json={**_DXM, "claim_id": "R_ovrA"}).json()
    assert "DX_ACCIDENT_MISMATCH" in r["reasons"]                          # SCORED by default -> visible
    _login("admin")
    try:
        client.post("/api/admin/signal-modes",
                    json={"code": "DX_ACCIDENT_MISMATCH", "mode": "SHADOW", "note": "low precision"})
        _login("handler")
        # a different service date: the identical line on a second claim for the same party would
        # now be SUPPLIER_PRECLUSION (pay once across claims, H2) before the DX check runs
        line_b = {**_DXM["lines"][0], "service_date": "2026-03-02"}
        r2 = client.post("/api/claims", json={**_DXM, "claim_id": "R_ovrB", "lines": [line_b]}).json()
        assert "DX_ACCIDENT_MISMATCH" not in r2["reasons"]                 # now suppressed from scoring
        assert "DX_ACCIDENT_MISMATCH" in r2["shadow_signals"]              # computed, invisible, 0 points
        _login("admin")
        audit = client.get("/api/admin/audit").json()
        assert any(a["action"] == "signal_mode.set" and a["target"] == "DX_ACCIDENT_MISMATCH"
                   for a in audit)
    finally:                                                              # restore so other tests are unaffected
        _login("admin")
        client.delete("/api/admin/signal-modes/DX_ACCIDENT_MISMATCH")


def test_last_active_administrator_cannot_be_removed():
    _login("admin")
    others = [u["username"] for u in client.get("/api/admin/users").json()
              if u["role"] == "ADMIN" and u["active"] and u["username"] != "admin"]
    try:
        for name in others:
            assert client.post(f"/api/admin/users/{name}/active", json={"active": False}).status_code == 200
        r = client.post("/api/admin/users/admin/role", json={"role": "HANDLER"})
        assert r.status_code == 400 and "last active administrator" in r.json()["detail"]
        assert client.post("/api/admin/users/admin/role", json={"role": "ADMIN"}).status_code == 200   # no change is fine
    finally:
        for name in others:
            assert client.post(f"/api/admin/users/{name}/active", json={"active": True}).status_code == 200
    # with another administrator active, the guard does not bite: deactivating one of several is allowed
    if others:
        assert client.post(f"/api/admin/users/{others[0]}/active", json={"active": False}).status_code == 200
        assert client.post(f"/api/admin/users/{others[0]}/active", json={"active": True}).status_code == 200


def test_audit_search_filters_and_pages():
    _login("admin")
    client.post("/api/admin/caps", json={"effective_from": "2031-04-01", "annual_cap": 411000})
    client.post("/api/admin/preauth", json={"code": "AUDSRCH1"})
    client.delete("/api/admin/preauth/AUDSRCH1")
    get = lambda **p: client.get("/api/admin/audit/search", params=p).json()

    caps = get(area="cap")
    assert caps["total"] >= 1 and all(r["action"].startswith("cap.") for r in caps["rows"])
    hit = get(q="AUDSRCH1")
    assert hit["total"] == 2 and [r["action"] for r in hit["rows"]] == ["preauth.remove", "preauth.add"]   # newest first
    assert get(q="AUDSRCH1", actor="nobody")["total"] == 0
    assert get(q="AUDSRCH1", actor="admin")["total"] == 2
    page = get(q="AUDSRCH1", limit=1, offset=1)
    assert page["total"] == 2 and [r["action"] for r in page["rows"]] == ["preauth.add"]
    assert get(q="AUDSRCH1", date_from="2099-01-01")["total"] == 0
    assert get(q="AUDSRCH1", date_to="2000-01-01")["total"] == 0

    facets = client.get("/api/admin/audit/facets").json()
    assert "admin" in facets["actors"] and {"cap", "preauth"} <= set(facets["areas"])
    client.delete("/api/admin/caps/2031-04-01")
    _login("handler")
    assert client.get("/api/admin/audit/search").status_code == 403
