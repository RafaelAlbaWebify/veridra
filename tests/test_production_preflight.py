from __future__ import annotations

import json
from pathlib import Path

import pytest

from veridra.production_preflight import PreflightStatus, run_production_preflight


def _clear(monkeypatch: pytest.MonkeyPatch) -> None:
    names = (
        "VERIDRA_ENV",
        "VERIDRA_IDENTITY_DB",
        "VERIDRA_TENANT_DATA_ROOT",
        "VERIDRA_TRUSTED_ORIGIN",
        "VERIDRA_ALLOWED_HOSTS",
        "VERIDRA_PRIVACY_URL",
        "VERIDRA_TERMS_URL",
        "VERIDRA_SMTP_HOST",
        "VERIDRA_SMTP_SENDER",
        "VERIDRA_SMTP_USERNAME",
        "VERIDRA_SMTP_PASSWORD",
        "VERIDRA_STRIPE_SECRET_KEY",
        "VERIDRA_STRIPE_WEBHOOK_SECRET",
        "VERIDRA_STRIPE_WEBHOOK_SECRET_PREVIOUS",
        "VERIDRA_STRIPE_PRICE_SOLO",
        "VERIDRA_STRIPE_PRICE_PROFESSIONAL",
        "VERIDRA_STRIPE_PRICE_AGENCY",
    )
    for name in names:
        monkeypatch.delenv(name, raising=False)


def _valid_required(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("VERIDRA_ENV", "production")
    monkeypatch.setenv(
        "VERIDRA_IDENTITY_DB",
        str((tmp_path / "identity" / "veridra.sqlite3").resolve()),
    )
    monkeypatch.setenv(
        "VERIDRA_TENANT_DATA_ROOT",
        str((tmp_path / "tenants").resolve()),
    )
    monkeypatch.setenv("VERIDRA_TRUSTED_ORIGIN", "https://app.example.com")
    monkeypatch.setenv("VERIDRA_ALLOWED_HOSTS", "app.example.com")
    monkeypatch.setenv("VERIDRA_PRIVACY_URL", "https://example.com/privacy")
    monkeypatch.setenv("VERIDRA_TERMS_URL", "https://example.com/terms")
    monkeypatch.setenv("VERIDRA_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("VERIDRA_SMTP_SENDER", "security@example.com")


def _enable_stripe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VERIDRA_STRIPE_SECRET_KEY", "sk_test_preflight")
    monkeypatch.setenv("VERIDRA_STRIPE_WEBHOOK_SECRET", "whsec_preflight")
    monkeypatch.setenv("VERIDRA_STRIPE_PRICE_SOLO", "price_solo")
    monkeypatch.setenv("VERIDRA_STRIPE_PRICE_PROFESSIONAL", "price_professional")
    monkeypatch.setenv("VERIDRA_STRIPE_PRICE_AGENCY", "price_agency")


def test_invalid_production_configuration_is_critical(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear(monkeypatch)

    result = run_production_preflight()

    assert result.status is PreflightStatus.critical
    assert result.exit_code == 2
    assert not result.ready


def test_valid_required_configuration_is_free_launch_ready_with_warning(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _valid_required(monkeypatch, tmp_path)

    result = run_production_preflight()

    assert result.status is PreflightStatus.warning
    assert result.exit_code == 1
    assert result.ready
    checks = {check.name: check.status for check in result.checks}
    assert checks == {
        "runtime": PreflightStatus.ok,
        "storage": PreflightStatus.ok,
        "legal": PreflightStatus.ok,
        "smtp": PreflightStatus.ok,
        "stripe": PreflightStatus.warning,
    }


def test_overlapping_identity_and_tenant_storage_is_critical(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _valid_required(monkeypatch, tmp_path)
    tenant_root = (tmp_path / "durable").resolve()
    monkeypatch.setenv("VERIDRA_TENANT_DATA_ROOT", str(tenant_root))
    monkeypatch.setenv(
        "VERIDRA_IDENTITY_DB",
        str((tenant_root / "identity.sqlite3").resolve()),
    )

    result = run_production_preflight()

    checks = {check.name: check for check in result.checks}
    assert result.status is PreflightStatus.critical
    assert checks["storage"].status is PreflightStatus.critical
    assert "distinct" in checks["storage"].message


def test_existing_invalid_storage_shapes_are_critical(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _valid_required(monkeypatch, tmp_path)
    identity = tmp_path / "identity" / "veridra.sqlite3"
    identity.mkdir(parents=True)

    result = run_production_preflight()

    checks = {check.name: check for check in result.checks}
    assert result.status is PreflightStatus.critical
    assert checks["storage"].status is PreflightStatus.critical
    assert "file" in checks["storage"].message


def test_require_stripe_makes_absent_billing_critical(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _valid_required(monkeypatch, tmp_path)

    result = run_production_preflight(require_stripe=True)

    assert result.status is PreflightStatus.critical
    assert result.exit_code == 2
    assert not result.ready


def test_previous_webhook_secret_without_stripe_is_critical(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _valid_required(monkeypatch, tmp_path)
    monkeypatch.setenv("VERIDRA_STRIPE_WEBHOOK_SECRET_PREVIOUS", "whsec_previous")

    result = run_production_preflight()

    checks = {check.name: check for check in result.checks}
    assert result.status is PreflightStatus.critical
    assert checks["stripe"].status is PreflightStatus.critical


def test_invalid_webhook_secret_overlap_is_critical(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _valid_required(monkeypatch, tmp_path)
    _enable_stripe(monkeypatch)
    monkeypatch.setenv("VERIDRA_STRIPE_WEBHOOK_SECRET_PREVIOUS", "whsec_preflight")

    result = run_production_preflight(require_stripe=True)

    checks = {check.name: check for check in result.checks}
    assert result.status is PreflightStatus.critical
    assert checks["stripe"].status is PreflightStatus.critical


def test_valid_webhook_secret_overlap_is_paid_launch_ready(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _valid_required(monkeypatch, tmp_path)
    _enable_stripe(monkeypatch)
    monkeypatch.setenv("VERIDRA_STRIPE_WEBHOOK_SECRET_PREVIOUS", "whsec_previous")

    result = run_production_preflight(require_stripe=True)
    payload = json.dumps(result.as_dict(), sort_keys=True)

    assert result.status is PreflightStatus.ok
    assert result.ready
    assert "whsec_preflight" not in payload
    assert "whsec_previous" not in payload


def test_complete_paid_launch_configuration_is_ready_and_secret_free(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _valid_required(monkeypatch, tmp_path)
    _enable_stripe(monkeypatch)

    result = run_production_preflight(require_stripe=True)
    payload = json.dumps(result.as_dict(), sort_keys=True)

    assert result.status is PreflightStatus.ok
    assert result.exit_code == 0
    assert result.ready
    assert all(check.status is PreflightStatus.ok for check in result.checks)
    assert "sk_test_preflight" not in payload
    assert "whsec_preflight" not in payload
    assert "price_agency" not in payload
    assert "app.example.com" not in payload
    assert str(tmp_path) not in payload
