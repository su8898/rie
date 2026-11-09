"""Runtime configuration (env-driven). SQLite by default so the stack runs hermetically;
point RIE_DATABASE_URL at PostgreSQL 16 in production (the schema is portable).

Secrets have *dev* defaults so tests and local runs need no setup — but the app REFUSES to start
with any default secret unless RIE_APP_ENV is `dev` or `test` (`check_secrets()`, called from
`server.main` at import). Dev users (`admin/admin`, ...) are seeded only in dev/test, or when
RIE_SEED_DEV_USERS=1; production bootstraps a single ADMIN from RIE_BOOTSTRAP_ADMIN_PASSWORD.
"""
from __future__ import annotations

import os

DATABASE_URL = os.environ.get("RIE_DATABASE_URL", "sqlite:///./rie.db")
PAGE_SIZE = int(os.environ.get("RIE_PAGE_SIZE", "25"))
APP_ENV = os.environ.get("RIE_APP_ENV", "dev").lower()
IS_DEV = APP_ENV in ("dev", "test")

# Dev defaults — every one of these is refused outside dev/test by check_secrets().
_DEFAULTS = {
    "RIE_SECRET_KEY": "dev-insecure-change-me",
    "RIE_RAILS_SECRET": "rie-rails-dev-secret",
    "RIE_PSEUDONYM_SECRET": "rie-pseudonym-dev-secret",
}
SECRET_KEY = os.environ.get("RIE_SECRET_KEY", _DEFAULTS["RIE_SECRET_KEY"])
# Shared HS256 secret for the provider->fund submission rails (per-switch ES256 keys in prod).
RAILS_SECRET = os.environ.get("RIE_RAILS_SECRET", _DEFAULTS["RIE_RAILS_SECRET"])
# POPIA pseudonymisation HMAC key — raw national IDs are HMAC'd to P_* tokens at ingest (§2/§4/§9).
PSEUDONYM_SECRET = os.environ.get("RIE_PSEUDONYM_SECRET", _DEFAULTS["RIE_PSEUDONYM_SECRET"])

# Dev-user seeding (username == password) — dev/test only unless explicitly forced.
SEED_DEV_USERS = IS_DEV or os.environ.get("RIE_SEED_DEV_USERS", "") == "1"
# Production bootstrap: when the user table is empty, create ONE ADMIN with this password.
BOOTSTRAP_ADMIN_PASSWORD = os.environ.get("RIE_BOOTSTRAP_ADMIN_PASSWORD", "")

_MIN_SECRET_LEN = 32


def insecure_secrets(env: dict | None = None) -> list[str]:
    """Names of secrets that are still at their dev default or too short (given an env mapping)."""
    e = os.environ if env is None else env
    bad = []
    for name, default in _DEFAULTS.items():
        val = e.get(name, default)
        if val == default or len(val) < _MIN_SECRET_LEN:
            bad.append(name)
    return bad


def check_secrets(env: dict | None = None) -> None:
    """Raise RuntimeError when running outside dev/test with default or weak secrets."""
    e = os.environ if env is None else env
    app_env = e.get("RIE_APP_ENV", "dev").lower()
    if app_env in ("dev", "test"):
        return
    bad = insecure_secrets(e)
    if bad:
        raise RuntimeError(
            f"RIE_APP_ENV={app_env}: refusing to start with default/weak secrets: {', '.join(bad)} "
            f"(each must be set to >= {_MIN_SECRET_LEN} random characters)")
