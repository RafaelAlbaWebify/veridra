from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


class SignupLegalEvidenceError(RuntimeError):
    pass


@dataclass(frozen=True)
class SignupLegalAcceptance:
    token_hash: str
    tenant_slug: str
    owner_email: str
    owner_name: str
    terms_url: str
    privacy_url: str
    accepted_at: datetime
    activated_at: datetime | None
    tenant_id: str | None
    user_id: str | None


class SQLiteSignupLegalEvidenceStore:
    def __init__(self, database: Path) -> None:
        self.database = database

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @staticmethod
    def _token_hash(token: str) -> str:
        if len(token) < 32:
            raise SignupLegalEvidenceError("Signup token is invalid.")
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def initialize(self) -> None:
        try:
            with self._connect() as connection:
                connection.execute(
                    """CREATE TABLE IF NOT EXISTS signup_legal_acceptances (
                        token_hash TEXT PRIMARY KEY,
                        tenant_slug TEXT NOT NULL,
                        owner_email TEXT NOT NULL,
                        owner_name TEXT NOT NULL,
                        terms_url TEXT NOT NULL,
                        privacy_url TEXT NOT NULL,
                        accepted_at TEXT NOT NULL,
                        activated_at TEXT,
                        tenant_id TEXT,
                        user_id TEXT
                    )"""
                )
                connection.execute(
                    """CREATE INDEX IF NOT EXISTS signup_legal_acceptances_email_idx
                    ON signup_legal_acceptances(owner_email, accepted_at)"""
                )
        except sqlite3.Error as exc:
            raise SignupLegalEvidenceError(
                "Signup legal evidence store could not be initialized."
            ) from exc

    def record_pending(
        self,
        *,
        token: str,
        tenant_slug: str,
        owner_email: str,
        owner_name: str,
        terms_url: str,
        privacy_url: str,
        accepted_at: datetime | None = None,
    ) -> None:
        recorded_at = (accepted_at or datetime.now(UTC)).astimezone(UTC)
        token_hash = self._token_hash(token)
        self.initialize()
        try:
            with self._connect() as connection:
                connection.execute(
                    """INSERT INTO signup_legal_acceptances
                    (token_hash, tenant_slug, owner_email, owner_name, terms_url,
                     privacy_url, accepted_at, activated_at, tenant_id, user_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL)""",
                    (
                        token_hash,
                        tenant_slug,
                        owner_email,
                        owner_name,
                        terms_url,
                        privacy_url,
                        recorded_at.isoformat(),
                    ),
                )
        except sqlite3.Error as exc:
            raise SignupLegalEvidenceError(
                "Signup legal acceptance could not be recorded."
            ) from exc

    def cancel(self, token: str) -> None:
        token_hash = self._token_hash(token)
        self.initialize()
        try:
            with self._connect() as connection:
                connection.execute(
                    "DELETE FROM signup_legal_acceptances WHERE token_hash = ?",
                    (token_hash,),
                )
        except sqlite3.Error as exc:
            raise SignupLegalEvidenceError(
                "Signup legal acceptance could not be discarded."
            ) from exc

    def mark_activated(
        self,
        *,
        token: str,
        tenant_id: str,
        user_id: str,
        activated_at: datetime | None = None,
    ) -> None:
        token_hash = self._token_hash(token)
        recorded_at = (activated_at or datetime.now(UTC)).astimezone(UTC)
        self.initialize()
        try:
            with self._connect() as connection:
                updated = connection.execute(
                    """UPDATE signup_legal_acceptances
                    SET activated_at = ?, tenant_id = ?, user_id = ?
                    WHERE token_hash = ? AND activated_at IS NULL""",
                    (recorded_at.isoformat(), tenant_id, user_id, token_hash),
                )
                if updated.rowcount != 1:
                    raise SignupLegalEvidenceError(
                        "Signup legal acceptance is unavailable for activation."
                    )
        except sqlite3.Error as exc:
            raise SignupLegalEvidenceError(
                "Signup legal acceptance could not be activated."
            ) from exc

    def latest_for_email(self, owner_email: str) -> SignupLegalAcceptance | None:
        self.initialize()
        try:
            with self._connect() as connection:
                row = connection.execute(
                    """SELECT * FROM signup_legal_acceptances
                    WHERE owner_email = ? ORDER BY accepted_at DESC LIMIT 1""",
                    (owner_email,),
                ).fetchone()
        except sqlite3.Error as exc:
            raise SignupLegalEvidenceError(
                "Signup legal acceptance could not be read."
            ) from exc
        if row is None:
            return None
        return SignupLegalAcceptance(
            token_hash=row["token_hash"],
            tenant_slug=row["tenant_slug"],
            owner_email=row["owner_email"],
            owner_name=row["owner_name"],
            terms_url=row["terms_url"],
            privacy_url=row["privacy_url"],
            accepted_at=datetime.fromisoformat(row["accepted_at"]),
            activated_at=(
                datetime.fromisoformat(row["activated_at"])
                if row["activated_at"] is not None
                else None
            ),
            tenant_id=row["tenant_id"],
            user_id=row["user_id"],
        )
