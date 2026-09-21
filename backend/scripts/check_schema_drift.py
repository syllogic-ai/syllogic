#!/usr/bin/env python3
"""Diffs the live (Drizzle-migrated) database schema against the
SQLAlchemy models in app/models.py.

Drizzle owns migrations; the SQLAlchemy models mirror them by hand for the
backend's ORM. Nothing enforced that they stay in sync, so a column added
on the Drizzle side could silently be invisible to the backend until
something fails in production. This script closes that gap: it reflects
every table it can find in the database and compares column sets against
the corresponding SQLAlchemy model, for every table SQLAlchemy actually
maps.

Tables that exist in the database but aren't mapped in models.py at all
(e.g. better-auth's own oauth_* tables, or newer Drizzle-only tables the
backend doesn't touch yet) are intentionally not modeled here and are
reported as informational only, not a failure -- this checks "does the
backend's picture of the tables it uses match reality," not "does
SQLAlchemy mirror 100% of the Drizzle schema."

Usage:
    DATABASE_URL=postgresql://... python scripts/check_schema_drift.py
    DATABASE_URL=postgresql://... python scripts/check_schema_drift.py --ignore-extra-columns

Exit code is non-zero (and CI should fail) only when a table SQLAlchemy
maps is missing entirely, or its column set doesn't match the database.

`--ignore-extra-columns` narrows that to "everything the models need exists",
reporting columns the database has but the models don't as informational.
That is the question scripts/test-backend.sh asks before running the suite:
a column the models never reference cannot break a test, and gating the test
run on unrelated pre-existing drift would just stop anyone running tests.
"""

from __future__ import annotations

import os
import sys

from sqlalchemy import MetaData, create_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import Base  # noqa: E402
import app.models  # noqa: E402, F401 -- registers every table on Base.metadata


def main() -> int:
    ignore_extra_columns = "--ignore-extra-columns" in sys.argv[1:]
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL is required", file=sys.stderr)
        return 2

    engine = create_engine(database_url)
    live = MetaData()
    live.reflect(bind=engine)

    errors: list[str] = []
    info: list[str] = []

    for table_name, model_table in Base.metadata.tables.items():
        live_table = live.tables.get(table_name)
        if live_table is None:
            errors.append(
                f"table '{table_name}' is mapped in app/models.py but missing from the database"
            )
            continue

        model_columns = set(model_table.columns.keys())
        live_columns = set(live_table.columns.keys())

        missing_in_db = model_columns - live_columns
        missing_in_model = live_columns - model_columns

        if missing_in_db:
            errors.append(
                f"table '{table_name}': column(s) {sorted(missing_in_db)} are in app/models.py "
                "but missing from the database"
            )
        if missing_in_model and ignore_extra_columns:
            info.append(
                f"table '{table_name}': column(s) {sorted(missing_in_model)} exist in the database "
                "but aren't in app/models.py (ignored)"
            )
        elif missing_in_model:
            errors.append(
                f"table '{table_name}': column(s) {sorted(missing_in_model)} exist in the database "
                "but aren't in app/models.py"
            )

    unmapped_tables = set(live.tables.keys()) - set(Base.metadata.tables.keys())
    if unmapped_tables:
        info.append(
            "tables in the database with no SQLAlchemy model (informational, not an error): "
            + ", ".join(sorted(unmapped_tables))
        )

    for line in info:
        print(f"[info] {line}")

    if errors:
        print(f"\nSchema drift detected ({len(errors)} issue(s)):", file=sys.stderr)
        for line in errors:
            print(f"  - {line}", file=sys.stderr)
        print(
            "\nUpdate app/models.py (backend) to match the Drizzle migration "
            "(frontend/lib/db/schema.ts + migrations), or vice versa.",
            file=sys.stderr,
        )
        return 1

    print(f"No schema drift: {len(Base.metadata.tables)} mapped table(s) match the database.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
