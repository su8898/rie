"""Alembic environment.

Targets the server's SQLAlchemy metadata (server.models) and reads the database URL from
RIE_DATABASE_URL via server.config — the same source the app uses — so `alembic upgrade head`
migrates whichever database the app is pointed at (SQLite dev / PostgreSQL 16 prod). Batch mode is
enabled on SQLite so future ALTERs work there too.
"""
from __future__ import annotations

import os
import sys

from alembic import context
from sqlalchemy import engine_from_config, pool

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from server import models  # noqa: E402,F401  (import populates Base.metadata)
from server.config import DATABASE_URL  # noqa: E402
from server.db import Base  # noqa: E402

config = context.config
config.set_main_option("sqlalchemy.url", DATABASE_URL)
target_metadata = Base.metadata
_is_sqlite = DATABASE_URL.startswith("sqlite")


def run_migrations_offline() -> None:
    context.configure(url=DATABASE_URL, target_metadata=target_metadata, literal_binds=True,
                      compare_type=True, render_as_batch=_is_sqlite,
                      dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(config.get_section(config.config_ini_section, {}),
                                     prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata,
                          compare_type=True, render_as_batch=_is_sqlite)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_offline() if context.is_offline_mode() else run_migrations_online()
