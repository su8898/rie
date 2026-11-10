"""Detached JWS over canonical JSON — HS256 (stdlib) and ES256 (ECDSA P-256).

The signature covers a canonical (sorted-key, whitespace-free) rendering of the JSON body, so it
survives HTTP re-serialisation: both sides canonicalise identically. Token form is
`base64url(header)..base64url(signature)` — the doubled dot marks the payload as detached (RFC 7797
style).

HS256 is the shared-secret form the channel started with. ES256 is the production form (ported
from CIE's interface standard): each connecting party signs with its own private key and the Fund
holds only the public key, so a signature identifies its signer and cannot be repudiated. ES256
needs the `cryptography` package, imported only when an ES256 operation runs.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
from typing import Optional


def _b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _b64u_dec(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def canonical(obj) -> bytes:
    return json.dumps(obj, separators=(",", ":"), sort_keys=True).encode()


def sign_detached(header: dict, body_obj, secret) -> str:
    """`secret` is the shared secret (HS256) or an EC private key (header alg ES256)."""
    h = _b64u(canonical(header))
    b = _b64u(canonical(body_obj))
    if header.get("alg") == "ES256":
        return f"{h}..{_es_sign(secret, f'{h}.{b}')}"
    mac = hmac.new(secret.encode(), f"{h}.{b}".encode(), hashlib.sha256).digest()
    return f"{h}..{_b64u(mac)}"                       # detached: payload omitted between the dots


def peek_header(token) -> Optional[dict]:
    """The protected header of a detached JWS, UNVERIFIED — only to learn which key to verify with."""
    try:
        h, empty, _sig = token.split(".")
        header = json.loads(_b64u_dec(h))
    except Exception:
        return None
    return header if empty == "" and isinstance(header, dict) else None


def verify_detached(token: str, body_obj, secret: str) -> Optional[dict]:
    """Return the decoded protected header if the signature is valid over body_obj, else None."""
    try:
        h, empty, m = token.split(".")
    except (ValueError, AttributeError):
        return None
    if empty != "":                                  # must be the detached (..) form
        return None
    b = _b64u(canonical(body_obj))
    expected = hmac.new(secret.encode(), f"{h}.{b}".encode(), hashlib.sha256).digest()
    try:
        if not hmac.compare_digest(_b64u_dec(m), expected):
            return None
        header = json.loads(_b64u_dec(h))
        if not isinstance(header, dict) or header.get("alg") != "HS256":   # alg pinned — no 'none'
            return None
        return header
    except Exception:
        return None


# ── ES256 (ECDSA P-256 over SHA-256) ─────────────────────────────────────────
def _ec():
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec, utils
    return ec, utils, hashes, serialization


def generate_key():
    """A fresh P-256 private key."""
    return _ec()[0].generate_private_key(_ec()[0].SECP256R1())


def private_pem(key) -> str:
    _ec_, _utils, _hashes, ser = _ec()
    return key.private_bytes(ser.Encoding.PEM, ser.PrivateFormat.PKCS8, ser.NoEncryption()).decode()


def load_private_key(pem: str):
    return _ec()[3].load_pem_private_key(pem.encode(), password=None)


def public_jwk(key, kid: Optional[str] = None) -> dict:
    """The public half of a private (or public) EC key as a JWK."""
    pub = key.public_key() if hasattr(key, "public_key") else key
    n = pub.public_numbers()
    jwk = {"kty": "EC", "crv": "P-256", "alg": "ES256", "use": "sig",
           "x": _b64u(n.x.to_bytes(32, "big")), "y": _b64u(n.y.to_bytes(32, "big"))}
    return {**jwk, "kid": kid} if kid else jwk


def thumbprint(jwk: dict) -> str:
    """RFC 7638 thumbprint of an EC public JWK — a stable key id."""
    required = {"crv": jwk["crv"], "kty": jwk["kty"], "x": jwk["x"], "y": jwk["y"]}
    return _b64u(hashlib.sha256(canonical(required)).digest())


def _public_key(jwk: dict):
    ec = _ec()[0]
    numbers = ec.EllipticCurvePublicNumbers(int.from_bytes(_b64u_dec(jwk["x"]), "big"),
                                            int.from_bytes(_b64u_dec(jwk["y"]), "big"), ec.SECP256R1())
    return numbers.public_key()                       # raises if the point is not on the curve


def clean_public_jwk(jwk) -> dict:
    """Validate a party's public key and return just its public members. Refuses anything that
    is not a P-256 public key — including a JWK that carries the private member `d`."""
    if not isinstance(jwk, dict) or jwk.get("kty") != "EC" or jwk.get("crv") != "P-256":
        raise ValueError("the key must be an EC P-256 public JWK (kty EC, crv P-256)")
    if "d" in jwk:
        raise ValueError("that is a PRIVATE key — register the public key only, and rotate this one")
    try:
        x, y = _b64u_dec(str(jwk["x"])), _b64u_dec(str(jwk["y"]))
        if len(x) != 32 or len(y) != 32:
            raise ValueError
        clean = {"kty": "EC", "crv": "P-256", "x": _b64u(x), "y": _b64u(y)}
        _public_key(clean)
    except Exception:
        raise ValueError("x and y must be the base64url coordinates of a point on P-256") from None
    return clean


def _es_sign(key, signing_input: str) -> str:
    ec, utils, hashes, _ser = _ec()
    r, s_ = utils.decode_dss_signature(key.sign(signing_input.encode(), ec.ECDSA(hashes.SHA256())))
    return _b64u(r.to_bytes(32, "big") + s_.to_bytes(32, "big"))      # JWS carries raw r||s, not DER


def verify_es256(token: str, body_obj, jwk: dict) -> Optional[dict]:
    """Return the protected header if `token` is a valid ES256 detached JWS over body_obj under
    the public key `jwk`, else None."""
    header = peek_header(token)
    if header is None or header.get("alg") != "ES256":                 # alg pinned
        return None
    try:
        ec, utils, hashes, _ser = _ec()
        h, _empty, sig = token.split(".")
        raw = _b64u_dec(sig)
        if len(raw) != 64:
            return None
        der = utils.encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big"))
        _public_key(jwk).verify(der, f"{h}.{_b64u(canonical(body_obj))}".encode(), ec.ECDSA(hashes.SHA256()))
        return header
    except Exception:
        return None
