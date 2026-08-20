from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from veridra.password_recovery_throttle import SQLitePasswordRecoveryThrottle

NOW = datetime(2026, 8, 20, 15, 0, tzinfo=UTC)


def test_recovery_throttle_normalizes_subject_and_persists_lockout(tmp_path: Path) -> None:
    database = tmp_path / "identity.sqlite3"
    first = SQLitePasswordRecoveryThrottle(database)

    assert first.consume(email=" Owner@Example.com ", now=NOW).allowed
    assert first.consume(email="owner@example.com", now=NOW + timedelta(minutes=1)).allowed
    assert first.consume(email="OWNER@EXAMPLE.COM", now=NOW + timedelta(minutes=2)).allowed
    denied = first.consume(email="owner@example.com", now=NOW + timedelta(minutes=3))

    assert not denied.allowed
    assert denied.retry_after_seconds == 900

    second = SQLitePasswordRecoveryThrottle(database)
    persisted = second.consume(email="owner@example.com", now=NOW + timedelta(minutes=4))

    assert not persisted.allowed
    assert persisted.retry_after_seconds == 840


def test_recovery_throttle_is_per_address_and_recovers_after_lockout(tmp_path: Path) -> None:
    database = tmp_path / "identity.sqlite3"
    throttle = SQLitePasswordRecoveryThrottle(database)

    for minute in range(3):
        assert throttle.consume(
            email="owner@example.com",
            now=NOW + timedelta(minutes=minute),
        ).allowed
    assert not throttle.consume(
        email="owner@example.com",
        now=NOW + timedelta(minutes=3),
    ).allowed

    assert throttle.consume(
        email="other@example.com",
        now=NOW + timedelta(minutes=4),
    ).allowed
    assert throttle.consume(
        email="owner@example.com",
        now=NOW + timedelta(minutes=19),
    ).allowed


def test_recovery_throttle_does_not_store_plain_email(tmp_path: Path) -> None:
    database = tmp_path / "identity.sqlite3"
    throttle = SQLitePasswordRecoveryThrottle(database)

    throttle.consume(email="sensitive@example.com", now=NOW)

    assert b"sensitive@example.com" not in database.read_bytes()
