"""Runtime configuration (env-driven). SQLite by default so the stack runs hermetically;
point RIE_DATABASE_URL at PostgreSQL 16 in production (the schema is portable)."""
from __future__ import annotations

import os

DATABASE_URL = os.environ.get("RIE_DATABASE_URL", "sqlite:///./rie.db")
SECRET_KEY = os.environ.get("RIE_SECRET_KEY", "dev-insecure-change-me")
PAGE_SIZE = int(os.environ.get("RIE_PAGE_SIZE", "25"))
APP_ENV = os.environ.get("RIE_APP_ENV", "dev")
