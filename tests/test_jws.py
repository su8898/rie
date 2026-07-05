"""Detached-JWS unit tests — round-trip, tamper detection, canonicalisation."""
from __future__ import annotations

from server import jws


def test_sign_verify_roundtrip():
    body = {"b": 2, "a": [1, 2], "c": {"z": 1, "y": 2}}
    header = {"alg": "HS256", "jti": "n1", "exp": 123}
    tok = jws.sign_detached(header, body, "secret")
    assert jws.verify_detached(tok, body, "secret") == header


def test_key_order_independent():
    tok = jws.sign_detached({"alg": "HS256"}, {"a": 1, "b": 2}, "s")
    assert jws.verify_detached(tok, {"b": 2, "a": 1}, "s") is not None   # canonical -> order-free


def test_verify_rejects_tamper():
    body = {"a": 1}
    tok = jws.sign_detached({"alg": "HS256"}, body, "secret")
    assert jws.verify_detached(tok, {"a": 2}, "secret") is None          # body changed
    assert jws.verify_detached(tok, body, "wrong-secret") is None        # wrong key
    assert jws.verify_detached("garbage", body, "secret") is None        # malformed
    assert jws.verify_detached("h.notdetached.m", body, "secret") is None  # not the .. form
