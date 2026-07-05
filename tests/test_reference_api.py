"""Reference-data lookups over the seeded (demo) reference tables."""
from __future__ import annotations

import test_api  # noqa: F401  (sets RIE_DATABASE_URL + imports the app first)
from fastapi.testclient import TestClient
from server.main import app

client = TestClient(app)


def _login(user="handler"):
    assert client.post("/api/auth/login", json={"username": user, "password": user}).status_code == 200


def test_tariff_lookup_normalises_code():
    _login()
    t = client.get("/api/reference/tariffs", params={"code": "0190"}).json()   # -> normalised "190"
    rates = {r["discipline"]: r["rate"] for r in t}
    assert t[0]["code"] == "190" and rates["GP"] == 500.0 and rates["SPECIALIST"] == 700.0


def test_nappi_lookup():
    _login()
    n = client.get("/api/reference/nappi", params={"code": "700101"}).json()
    assert n and n[0]["sep"] == 88.40


def test_reference_requires_auth():
    client.post("/api/auth/logout")
    assert client.get("/api/reference/tariffs", params={"code": "0190"}).status_code == 401


def test_editions_endpoint_ok():
    _login()
    assert client.get("/api/reference/editions").status_code == 200   # empty under demo seed


def test_disciplines_endpoint():
    _login()
    d = client.get("/api/reference/disciplines").json()
    assert "GP" in d and "SPECIALIST" in d                            # demo seed disciplines


def test_awards_band_endpoint_computes_band():
    _login()
    r = client.get("/api/reference/awards",
                   params={"injury_class": "PARAPLEGIA", "severity": "SEVERE"}).json()
    assert r["n"] == 6 and r["robust"] is True and r["band_p25"] < r["band_p75"]


def test_awards_classes_endpoint():
    _login()
    names = {c["injury_class"] for c in client.get("/api/reference/awards/classes").json()}
    assert {"TBI", "PARAPLEGIA", "QUADRIPLEGIA"} <= names
