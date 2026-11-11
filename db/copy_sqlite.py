"""Copy the working data of a SQLite RIE database (a local rie.db) into the target database
(RIE_DATABASE_URL — PostgreSQL in the deployed stack).

    python db/copy_sqlite.py /refdata/rie.db            # refuses if the target already has claims
    python db/copy_sqlite.py /refdata/rie.db --replace  # empties the working tables first

What is copied: every table that has rows in the source, read and written through the app's own
table definitions so dates, booleans and JSON arrive as the right types. Columns the source does
not have yet (an older schema) take their defaults.

What is NOT copied:
  * app_users — a local database carries the username==password dev logins, which must never
    reach a deployed site. The target keeps its own users.
  * the reference tables db/load_reference.py fills from reference.db (tariffs, NAPPI, ICD-10,
    editions, coding rules, flat-rate exclusions) — the target already has them, and anything
    maintained there through the app is left alone.

Rows that point at a parent row which no longer exists (SQLite allows that, PostgreSQL does
not) are left out and counted in the output.

The whole copy is one transaction: it either lands completely or not at all.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, func, insert, inspect, select, text  # noqa: E402

from server import models  # noqa: E402,F401  (registers every table on Base.metadata)
from server.db import Base, engine  # noqa: E402

SKIP = {"app_users", "alembic_version",
        "ref_rpl", "ref_nappi_sep", "ref_icd10", "ref_edition", "ref_code_rule", "ref_non_bench"}
_CHUNK = 5_000


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    replace = "--replace" in sys.argv[1:]
    if len(args) != 1 or not os.path.isfile(args[0]):
        sys.exit("usage: python db/copy_sqlite.py PATH/TO/rie.db [--replace]")
    src = create_engine(f"sqlite:///{args[0]}")
    src_insp, dst_insp = inspect(src), inspect(engine)
    src_tables = set(src_insp.get_table_names())

    plan = []                                   # (table, columns present on both sides)
    with src.connect() as s:
        for t in Base.metadata.sorted_tables:   # parents before children
            if t.name in SKIP or t.name not in src_tables or not dst_insp.has_table(t.name):
                continue
            if not s.scalar(select(func.count()).select_from(t)):
                continue
            for fk in t.foreign_keys:
                if fk.column.table.name in SKIP:
                    sys.exit(f"{t.name} references {fk.column.table.name}, which is not copied")
            have = {c["name"] for c in src_insp.get_columns(t.name)}
            plan.append((t, [c for c in t.columns if c.name in have]))

        with engine.begin() as d:
            existing = d.scalar(select(func.count()).select_from(Base.metadata.tables["claims"]))
            if existing and not replace:
                sys.exit(f"the target already holds {existing} claims — nothing copied "
                         f"(pass --replace to overwrite the copied tables)")
            # Empty every table this script owns, not only the ones the source has rows for —
            # a target row in a table the source leaves empty may point at a row being replaced.
            for t in reversed(Base.metadata.sorted_tables):         # children first
                if t.name not in SKIP and dst_insp.has_table(t.name):
                    d.execute(t.delete())
            copied: dict = {}                   # table name -> the rows that were copied
            for t, cols in plan:
                rows = [dict(r) for r in s.execute(select(*cols)).mappings()]
                # SQLite does not enforce foreign keys, so a local database can hold rows whose
                # parent is gone (leftovers of deleted test claims). PostgreSQL refuses them;
                # leave them behind, and anything that hangs off them with it.
                before = len(rows)
                for fk in t.foreign_keys:
                    if fk.parent.name not in rows[0]:
                        continue
                    parent = fk.column.table.name
                    keys = {r[fk.column.name] for r in copied.get(parent, [])} if parent != t.name                         else {r[fk.column.name] for r in rows}
                    rows = [r for r in rows if r[fk.parent.name] is None or r[fk.parent.name] in keys]
                    if not rows:
                        break
                copied[t.name] = rows
                if before != len(rows):
                    print(f"  {t.name}: left out {before - len(rows)} rows whose parent row is missing")
                for i in range(0, len(rows), _CHUNK):
                    d.execute(insert(t), rows[i:i + _CHUNK])
                # A copied row brings its own id; move the id sequence past the highest one.
                pk = list(t.primary_key.columns)
                if engine.dialect.name == "postgresql" and len(pk) == 1:
                    seq = d.scalar(text("select pg_get_serial_sequence(:t, :c)"),
                                   {"t": t.name, "c": pk[0].name})
                    if seq:
                        d.execute(text(f"select setval('{seq}', (select max({pk[0].name}) from {t.name}))"))
                print(f"  {t.name}: {len(rows)}", flush=True)
    print(f"copied {len(plan)} tables from {args[0]}")


if __name__ == "__main__":
    main()
