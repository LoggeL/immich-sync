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


def _create_useraccount_table(engine: Engine) -> None:
    # Ensure useraccount table exists
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS useraccount (
                  id INTEGER PRIMARY KEY,
                  instance_id INTEGER NOT NULL,
                  username VARCHAR(255),
                  api_key TEXT NOT NULL,
                  created_at TIMESTAMP NOT NULL
                )
                """
            )
        )

    # Add foreign key column to instance if missing
    if not _column_exists(engine, "instance", "primary_user_id"):
        with engine.begin() as conn:
            # SQLite cannot add a column with a foreign key constraint in ALTER TABLE reliably.
            # Add the column without constraint. Logical FK is enforced at app level.
            conn.execute(text("ALTER TABLE instance ADD COLUMN primary_user_id INTEGER"))


def _create_auth_tables(engine: Engine) -> None:
    # authuser table
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS authuser (
                  id INTEGER PRIMARY KEY,
                  username VARCHAR(255) UNIQUE NOT NULL,
                  password_hash TEXT NOT NULL,
                  password_salt TEXT NOT NULL,
                  instance_base_url TEXT NOT NULL,
                  instance_api_key TEXT NOT NULL,
                  created_at TIMESTAMP NOT NULL
                )
                """
            )
        )
    # userinstance mapping table
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS userinstance (
                  id INTEGER PRIMARY KEY,
                  user_id INTEGER NOT NULL,
                  instance_id INTEGER NOT NULL,
                  created_at TIMESTAMP NOT NULL
                )
                """
            )
        )


def _create_groupmember_table(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS groupmember (
                  id INTEGER PRIMARY KEY,
                  sync_id INTEGER NOT NULL,
                  user_id INTEGER NOT NULL,
                  label VARCHAR(255) NOT NULL,
                  album_id TEXT NOT NULL,
                  size_limit_bytes INTEGER NOT NULL,
                  active BOOLEAN NOT NULL,
                  created_at TIMESTAMP NOT NULL,
                  updated_at TIMESTAMP NOT NULL
                )
                """
            )
        )

MIGRATIONS: List[Migration] = [
    ("2025-08-17-001-add-expires-on", _add_expires_on_to_syncgroup),
    ("2025-08-17-002-useraccount-and-instance-fk", _create_useraccount_table),
    ("2025-08-17-003-auth-user-and-link", _create_auth_tables),
    ("2025-08-17-004-groupmember", _create_groupmember_table),
]


def run_migrations(engine: Engine) -> None:
    _ensure_schema_migrations_table(engine)
    for mig_id, mig_fn in MIGRATIONS:
        if _is_applied(engine, mig_id):
            continue
        mig_fn(engine)
        _mark_applied(engine, mig_id)


