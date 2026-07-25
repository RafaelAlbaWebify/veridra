from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


class SchemaMigrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class AppliedMigration:
    version: int
    name: str
    applied_at: datetime


_MIGRATIONS: tuple[tuple[int, str, tuple[str, ...]], ...] = (
    (
        1,
        "normalize-user-emails",
        (
            "UPDATE users SET email = lower(trim(email))",
            "CREATE UNIQUE INDEX IF NOT EXISTS users_email_normalized_idx "
            "ON users(lower(email))",
        ),
    ),
)


class SQLiteSchemaVersionManager:
    def __init__(self, database: Path) -> None:
        self.database = database

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    applied_at TEXT NOT NULL
                )"""
            )

    def apply_all(self, *, applied_at: datetime | None = None) -> tuple[int, ...]:
        timestamp = (applied_at or datetime.now(UTC)).astimezone(UTC)
        self.initialize()
        applied: list[int] = []
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = {
                int(row["version"])
                for row in connection.execute(
                    "SELECT version FROM schema_migrations"
                ).fetchall()
            }
            for version, name, statements in _MIGRATIONS:
                if version in existing:
                    continue
                try:
                    for statement in statements:
                        connection.execute(statement)
                except sqlite3.IntegrityError as exc:
                    raise SchemaMigrationError(
                        f"Schema migration {version} ({name}) could not be applied safely."
                    ) from exc
                connection.execute(
                    """INSERT INTO schema_migrations (version, name, applied_at)
                    VALUES (?, ?, ?)""",
                    (version, name, timestamp.isoformat()),
                )
                applied.append(version)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return tuple(applied)

    def list_applied(self) -> tuple[AppliedMigration, ...]:
        self.initialize()
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT version, name, applied_at FROM schema_migrations
                ORDER BY version"""
            ).fetchall()
        return tuple(
            AppliedMigration(
                version=int(row["version"]),
                name=str(row["name"]),
                applied_at=datetime.fromisoformat(row["applied_at"]),
            )
            for row in rows
        )
