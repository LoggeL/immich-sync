from __future__ import annotations

from typing import Callable, List, Tuple

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


Migration = Tuple[str, Callable[[Engine], None]]


def _column_exists(engine: Engine, table_name: str, column_name: str) -> bool:
    inspector = inspect(engine)
    try:
        cols = inspector.get_columns(table_name)
    except Exception:
        return False
    return any(c.get("name") == column_name for c in cols)


def _ensure_schema_migrations_table(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                  id TEXT PRIMARY KEY
                )
                """
            )
        )


def _is_applied(engine: Engine, migration_id: str) -> bool:
    _ensure_schema_migrations_table(engine)
    with engine.begin() as conn:
        result = conn.execute(text("SELECT 1 FROM schema_migrations WHERE id = :id"), {"id": migration_id})
        return result.first() is not None


def _mark_applied(engine: Engine, migration_id: str) -> None:
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO schema_migrations (id) VALUES (:id)"), {"id": migration_id})


def _add_expires_on_to_syncgroup(engine: Engine) -> None:
    if _column_exists(engine, "syncgroup", "expires_on"):
        return
    dialect = engine.dialect.name
    with engine.begin() as conn:
        # DATE works on SQLite/Postgres/MySQL for a simple date column
        conn.execute(text("ALTER TABLE syncgroup ADD COLUMN expires_on DATE"))


MIGRATIONS: List[Migration] = [
    ("2025-08-17-001-add-expires-on", _add_expires_on_to_syncgroup),
]


def run_migrations(engine: Engine) -> None:
    _ensure_schema_migrations_table(engine)
    for mig_id, mig_fn in MIGRATIONS:
        if _is_applied(engine, mig_id):
            continue
        mig_fn(engine)
        _mark_applied(engine, mig_id)


