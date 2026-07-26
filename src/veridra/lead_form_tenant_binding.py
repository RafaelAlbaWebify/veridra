from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


class LeadFormTenantBindingError(RuntimeError):
    pass


@dataclass(frozen=True)
class LeadFormTenantBinding:
    form_id: str
    tenant_id: str
    created_by_user_id: str
    created_at: datetime


class SQLiteLeadFormTenantBindingStore:
    def __init__(self, database: Path) -> None:
        self.database = database

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS lead_form_tenant_bindings (
                    form_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    created_by_user_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (tenant_id) REFERENCES tenants(id),
                    FOREIGN KEY (created_by_user_id) REFERENCES users(id)
                )"""
            )

    def bind(
        self,
        *,
        form_id: str,
        tenant_id: str,
        created_by_user_id: str,
        created_at: datetime | None = None,
    ) -> LeadFormTenantBinding:
        if len(form_id) != 24 or any(char not in "0123456789abcdef" for char in form_id):
            raise LeadFormTenantBindingError("Lead form identifier is invalid.")
        timestamp = (created_at or datetime.now(UTC)).astimezone(UTC)
        self.initialize()
        try:
            with self._connect() as connection:
                connection.execute(
                    """INSERT INTO lead_form_tenant_bindings
                    (form_id, tenant_id, created_by_user_id, created_at)
                    VALUES (?, ?, ?, ?)""",
                    (form_id, tenant_id, created_by_user_id, timestamp.isoformat()),
                )
        except sqlite3.IntegrityError as exc:
            raise LeadFormTenantBindingError("Lead form is already tenant-bound.") from exc
        return LeadFormTenantBinding(
            form_id=form_id,
            tenant_id=tenant_id,
            created_by_user_id=created_by_user_id,
            created_at=timestamp,
        )

    def resolve(self, form_id: str) -> LeadFormTenantBinding | None:
        self.initialize()
        with self._connect() as connection:
            row = connection.execute(
                """SELECT form_id, tenant_id, created_by_user_id, created_at
                FROM lead_form_tenant_bindings WHERE form_id = ?""",
                (form_id,),
            ).fetchone()
        if row is None:
            return None
        return LeadFormTenantBinding(
            form_id=row["form_id"],
            tenant_id=row["tenant_id"],
            created_by_user_id=row["created_by_user_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def unbind(self, *, form_id: str, tenant_id: str) -> None:
        self.initialize()
        with self._connect() as connection:
            deleted = connection.execute(
                """DELETE FROM lead_form_tenant_bindings
                WHERE form_id = ? AND tenant_id = ?""",
                (form_id, tenant_id),
            )
            if deleted.rowcount != 1:
                raise LeadFormTenantBindingError("Lead form binding was not found.")
