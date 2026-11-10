"""Reference client for the RIE provider channel — the template an integrator copies.

Self-contained: the standard library plus `cryptography`. It shows the whole of what a party's
system has to do: keep an ES256 private key, sign each request as a detached JWS over the
canonical JSON of its body (or, for a read, of the request's subject), and verify the Fund's
signature on the receipt against the Fund's published key.

    # 1. make a key pair; send the printed public key to the Fund to be registered
    python3 conformance/refclient.py keygen my-key.pem
    # 2. submit a claim
    python3 conformance/refclient.py submit --base http://localhost:8077 --party MY-PARTY \\
        --key my-key.pem claim.json
"""
from __future__ import annotations

import base64
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
import uuid

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, utils


# ── detached JWS, ES256 ──────────────────────────────────────────────────────
def b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def b64u_dec(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def canonical(obj) -> bytes:
    """The bytes both sides sign: sorted keys, no whitespace."""
    return json.dumps(obj, separators=(",", ":"), sort_keys=True).encode()


def sign(key, kid: str, obj, *, lifetime: int = 300, jti: str | None = None) -> str:
    """`header..signature` — the payload is detached (it travels as the HTTP body)."""
    header = {"alg": "ES256", "kid": kid, "exp": int(time.time()) + lifetime,
              "jti": jti or str(uuid.uuid4())}
    signing_input = f"{b64u(canonical(header))}.{b64u(canonical(obj))}"
    r, s = utils.decode_dss_signature(key.sign(signing_input.encode(), ec.ECDSA(hashes.SHA256())))
    return f"{signing_input.split('.')[0]}..{b64u(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}"


def verify(token: str, obj, jwk: dict) -> bool:
    """Is `token` a valid ES256 detached JWS over `obj` under the public key `jwk`?"""
    try:
        header_b64, empty, sig = token.split(".")
        raw = b64u_dec(sig)
        if empty or json.loads(b64u_dec(header_b64)).get("alg") != "ES256" or len(raw) != 64:
            return False
        pub = ec.EllipticCurvePublicNumbers(int.from_bytes(b64u_dec(jwk["x"]), "big"),
                                            int.from_bytes(b64u_dec(jwk["y"]), "big"),
                                            ec.SECP256R1()).public_key()
        der = utils.encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big"))
        pub.verify(der, f"{header_b64}.{b64u(canonical(obj))}".encode(), ec.ECDSA(hashes.SHA256()))
        return True
    except Exception:
        return False


def generate_key():
    return ec.generate_private_key(ec.SECP256R1())


def public_jwk(key) -> dict:
    n = key.public_key().public_numbers()
    return {"kty": "EC", "crv": "P-256", "x": b64u(n.x.to_bytes(32, "big")), "y": b64u(n.y.to_bytes(32, "big"))}


def save_key(key, path: str) -> None:
    with open(path, "w") as f:
        f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                  serialization.NoEncryption()).decode())


def load_key(path: str):
    with open(path, "rb") as f:
        return serialization.load_pem_private_key(f.read(), password=None)


# ── transport ────────────────────────────────────────────────────────────────
def http_transport(base: str):
    """(method, path, body, headers) -> (status, parsed JSON or text)."""
    def send(method: str, path: str, body, headers: dict):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(base.rstrip("/") + path, data=data, method=method,
                                     headers={"Content-Type": "application/json", **headers})
        try:
            with urllib.request.urlopen(req) as r:
                status, text = r.status, r.read().decode()
        except urllib.error.HTTPError as e:
            status, text = e.code, e.read().decode()
        try:
            return status, json.loads(text)
        except ValueError:
            return status, text
    return send


# ── the client ───────────────────────────────────────────────────────────────
class Client:
    def __init__(self, transport, party_id: str, key):
        self.send, self.party_id, self.key = transport, party_id, key
        self._fund_keys: dict | None = None

    def post(self, path: str, body, *, idem: str | None = None, signature: str | None = None):
        """A signed write. `idem` is the Idempotency-Key (a fresh one when omitted)."""
        headers = {"Idempotency-Key": idem or str(uuid.uuid4()),
                   "X-JWS-Signature": signature or sign(self.key, self.party_id, body)}
        return self.send("POST", path, body, headers)

    def get(self, path: str, subject: dict):
        """A signed read: the signature covers the request's subject, e.g. {"claimId": "…"}."""
        return self.send("GET", path, None, {"X-JWS-Signature": sign(self.key, self.party_id, subject)})

    def fund_keys(self) -> dict:
        """The Fund's published signing keys, by key id."""
        if self._fund_keys is None:
            _status, jwks = self.send("GET", "/rails/v1/.well-known/jwks.json", None, {})
            self._fund_keys = {k["kid"]: k for k in jwks["keys"]}
        return self._fund_keys

    def receipt_is_genuine(self, receipt: dict) -> bool:
        """Verify the Fund's signature on a receipt against its published key."""
        body = {k: v for k, v in receipt.items() if k != "signature"}
        try:
            kid = json.loads(b64u_dec(receipt["signature"].split(".")[0]))["kid"]
            return verify(receipt["signature"], body, self.fund_keys()[kid])
        except Exception:
            return False


def thumbprint(jwk: dict) -> str:
    return b64u(hashlib.sha256(canonical({k: jwk[k] for k in ("crv", "kty", "x", "y")})).digest())


def main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[0] == "keygen":
        key = generate_key()
        save_key(key, argv[1])
        print(f"private key written to {argv[1]} — keep it secret, never send it to anyone\n")
        print("public key to register with the Fund:")
        print(json.dumps(public_jwk(key), indent=2))
        return 0
    if len(argv) == 8 and argv[0] == "submit":
        opts = dict(zip(argv[1:7:2], argv[2:7:2]))
        client = Client(http_transport(opts["--base"]), opts["--party"], load_key(opts["--key"]))
        with open(argv[7]) as f:
            status, out = client.post("/rails/v1/claims", json.load(f))
        print(status, json.dumps(out, indent=2))
        if status == 200:
            print("receipt signature genuine:", client.receipt_is_genuine(out["receipt"]))
        return 0 if status == 200 else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
