"""Password hashing (stdlib PBKDF2 — no external dep) and the five RAF roles."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os

ROLES = ("HANDLER", "MEDICAL_OFFICER", "INVESTIGATOR", "LEGAL", "ADMIN")
_ITER = 100_000


def hash_password(pw: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, _ITER)
    return base64.b64encode(salt).decode() + "$" + base64.b64encode(dk).decode()


def verify_password(pw: str, stored: str) -> bool:
    try:
        s, d = stored.split("$")
        salt, dk = base64.b64decode(s), base64.b64decode(d)
    except Exception:
        return False
    return hmac.compare_digest(dk, hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, _ITER))
