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
    assert t and t[0]["code"] == "190" and t[0]["gp"] == 500.0 and t[0]["spec"] == 700.0


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
