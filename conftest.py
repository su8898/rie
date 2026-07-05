"""Put the repo root on sys.path so `engine`, `spec`, and `server` import cleanly under pytest,
and pin the DB to an isolated temp file BEFORE any test module imports `server`.

`server.db` builds its SQLAlchemy engine once, at import, from `RIE_DATABASE_URL`. If that is
unset the default is `./rie.db` — the developer DB, which in deployment holds the *real* RAF
reference. Whichever test module imports `server` first would then bind the whole suite to
`./rie.db`, so demo-seeded tests fail and results turn order-dependent. Pinning a fresh temp DB
here (conftest is imported before collection) makes the suite hermetic regardless of ordering."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(__file__))

if "RIE_DATABASE_URL" not in os.environ:
    _fd, _path = tempfile.mkstemp(suffix="-pytest-rie.db")
    os.close(_fd)
    os.environ["RIE_DATABASE_URL"] = "sqlite:///" + _path
