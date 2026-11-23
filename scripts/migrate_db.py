"""Bring the database schema to the latest revision — safe for any starting state.

Usage (from the repo root)::

    python -m scripts.migrate_db

Why this exists: the Alembic chain's first revision only adds indexes (it was
generated against tables that ``Base.metadata.create_all`` had already built),
so ``alembic upgrade head`` cannot build a schema from an empty database. This
script picks the correct path for each state:

* **Empty database** → create the full schema from the ORM models, then stamp
  Alembic at ``head``.
* **Alembic-versioned database** → ``alembic upgrade head`` (recent revisions
  are idempotent, so drift from ``create_all`` is tolerated).
* **Unversioned database with tables** (app ran but migrations never did) →
  create any missing tables; if every model column already exists, stamp
  ``head``; otherwise stop and list the missing columns instead of guessing.

Exit code is non-zero if the schema cannot be brought to head safely.
"""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import inspect

from alembic import command
from alembic.config import Config
from api.models import Base, engine

_ALEMBIC_INI: Path = Path(__file__).resolve().parent.parent / "alembic.ini"


def _missing_columns() -> list[str]:
    """Return ``table.column`` for every ORM column absent from the live DB."""
    insp = inspect(engine)
    missing: list[str] = []
    for table in Base.metadata.sorted_tables:
        if not insp.has_table(table.name):
            continue
        live = {c["name"] for c in insp.get_columns(table.name)}
        missing.extend(f"{table.name}.{col.name}" for col in table.columns if col.name not in live)
    return missing


def migrate() -> int:
    """Bring the configured database to Alembic head. Returns a process exit code."""
    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("script_location", str(_ALEMBIC_INI.parent / "alembic"))
    tables = set(inspect(engine).get_table_names())
    app_tables = tables - {"alembic_version"}

    if not app_tables:
        Base.metadata.create_all(bind=engine)
        command.stamp(cfg, "head")
        print("migrate_db: empty database — created schema and stamped head")
        return 0

    if "alembic_version" in tables:
        command.upgrade(cfg, "head")
        print("migrate_db: versioned database — upgraded to head")
        return 0

    Base.metadata.create_all(bind=engine)  # adds missing tables only
    missing = _missing_columns()
    if missing:
        print(
            "migrate_db: unversioned database is missing columns, refusing to stamp:\n  "
            + "\n  ".join(missing)
            + "\nStamp the revision that matches this schema "
            "(`alembic stamp <rev>`), then re-run this script.",
            file=sys.stderr,
        )
        return 1
    command.stamp(cfg, "head")
    print("migrate_db: unversioned database matches models — stamped head")
    return 0


if __name__ == "__main__":
    sys.exit(migrate())
