"""The server's clock. Every stored timestamp is UTC without an offset.

Columns that default to the database's `now()` are UTC on SQLite, so a time stamped in Python must
be UTC too; mixing in the machine's local time made two timestamps on the same record disagree by
the local offset. Business dates (an accident date, a lodgement date, "today" for prescription)
are calendar dates and stay with `date.today()`.
"""
from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    """The current time in UTC, naive, to match what the database's `now()` default stores."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
