from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from veridra.signup_legal_evidence import SQLiteSignupLegalEvidenceStore


TOKEN = "t" * 48
EMAIL = "owner@example.com"
TERMS = "https://legal.example.com/terms-v1"
PRIVACY = "https://legal.example.com/privacy-v1"


def _record(
    store: SQLiteSignupLegalEvidenceStore,
    *,
    accepted_at: datetime,
    expires_at: datetime,
) -> None:
    store.record_pending(
        token=TOKEN,
        tenant_slug="agency",
        owner_email=EMAIL,
        owner_name="Owner",
        terms_url=TERMS,
        privacy_url=PRIVACY,
        accepted_at=accepted_at,
        expires_at=expires_at,
    )


def test_pending_evidence_expires_with_signup_token(tmp_path: Path) -> None:
    store = SQLiteSignupLegalEvidenceStore(tmp_path / "identity.sqlite3")
    accepted_at = datetime(2026, 8, 21, 10, 0, tzinfo=UTC)
    expires_at = accepted_at + timedelta(minutes=30)
    _record(store, accepted_at=accepted_at, expires_at=expires_at)

    before_expiry = store.latest_for_email(
        EMAIL,
        now=accepted_at + timedelta(minutes=29),
    )
    after_expiry = store.latest_for_email(
        EMAIL,
        now=accepted_at + timedelta(minutes=31),
    )

    assert before_expiry is not None
    assert before_expiry.expires_at == expires_at
    assert after_expiry is None


def test_activated_evidence_survives_signup_expiry(tmp_path: Path) -> None:
    store = SQLiteSignupLegalEvidenceStore(tmp_path / "identity.sqlite3")
    accepted_at = datetime(2026, 8, 21, 10, 0, tzinfo=UTC)
    expires_at = accepted_at + timedelta(minutes=30)
    _record(store, accepted_at=accepted_at, expires_at=expires_at)
    activated_at = accepted_at + timedelta(minutes=5)

    assert store.mark_activated_if_present(
        token=TOKEN,
        tenant_id="a" * 24,
        user_id="b" * 24,
        activated_at=activated_at,
    )
    store.prune_expired_pending(now=accepted_at + timedelta(hours=1))
    evidence = store.latest_for_email(
        EMAIL,
        now=accepted_at + timedelta(hours=1),
    )

    assert evidence is not None
    assert evidence.activated_at == activated_at
    assert evidence.tenant_id == "a" * 24
    assert evidence.user_id == "b" * 24


def test_initialize_migrates_legacy_table_without_expiry(tmp_path: Path) -> None:
    database = tmp_path / "identity.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            """CREATE TABLE signup_legal_acceptances (
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

    SQLiteSignupLegalEvidenceStore(database).initialize()

    with sqlite3.connect(database) as connection:
        columns = {
            str(row[1])
            for row in connection.execute(
                "PRAGMA table_info(signup_legal_acceptances)"
            ).fetchall()
        }
    assert "expires_at" in columns
