from __future__ import annotations

from pathlib import Path

import pytest

from veridra.production_preflight import PreflightStatus, run_production_preflight


def _clear(monkeypatch: pytest.MonkeyPatch) -> None:
    names = (
        "VERIDRA_ENV",
        "VERIDRA_LOCAL_AGENCY",
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
    monkeypatch.setenv("VERIDRA_ENV", "local")
    monkeypatch.setenv(
        "VERIDRA_IDENTITY_DB",
        str((tmp_path / "identity" / "veridra.sqlite3").resolve()),
    )
    monkeypatch.setenv(
        "VERIDRA_TENANT_DATA_ROOT",
        str((tmp_path / "tenants").resolve()),
    )
    monkeypatch.setenv("VERIDRA_TRUSTED_ORIGIN", "http://127.0.0.1:8011")
    monkeypatch.setenv("VERIDRA_ALLOWED_HOSTS", "127.0.0.1")
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


def test_webify_local_preflight_is_ready_without_saas_billing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _valid_required(monkeypatch, tmp_path)
    monkeypatch.setenv("VERIDRA_TRUSTED_ORIGIN", "http://127.0.0.1:8011")
    monkeypatch.setenv("VERIDRA_ALLOWED_HOSTS", "127.0.0.1")

    result = run_production_preflight()

    assert result.ready
    checks = {check.name: check for check in result.checks}
    assert checks["webify-billing-boundary"].status is PreflightStatus.ok
    assert "external provider/accounting" in checks["webify-billing-boundary"].message


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
    assert "storage" in checks["storage"].name


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
    assert checks["storage"].message


def test_legacy_saas_billing_preflight_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _valid_required(monkeypatch, tmp_path)
    monkeypatch.setenv("VERIDRA_TRUSTED_ORIGIN", "http://127.0.0.1:8011")
    monkeypatch.setenv("VERIDRA_ALLOWED_HOSTS", "127.0.0.1")

    result = run_production_preflight(require_stripe=True)

    assert not result.ready
    checks = {check.name: check for check in result.checks}
    assert checks["webify-billing-boundary"].status is PreflightStatus.critical


def test_local_loopback_configuration_is_hardened_preflight_ready(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("VERIDRA_ENV", "local")
    monkeypatch.setenv(
        "VERIDRA_IDENTITY_DB",
        str((tmp_path / "identity" / "veridra.sqlite3").resolve()),
    )
    monkeypatch.setenv(
        "VERIDRA_TENANT_DATA_ROOT",
        str((tmp_path / "tenants").resolve()),
    )
    monkeypatch.setenv("VERIDRA_TRUSTED_ORIGIN", "http://127.0.0.1:8010")
    monkeypatch.setenv("VERIDRA_ALLOWED_HOSTS", "127.0.0.1,localhost")
    monkeypatch.setenv("VERIDRA_BIND_HOST", "127.0.0.1")
    monkeypatch.setenv("VERIDRA_BIND_PORT", "8010")
    monkeypatch.setenv("VERIDRA_PRIVACY_URL", "https://example.com/privacy")
    monkeypatch.setenv("VERIDRA_TERMS_URL", "https://example.com/terms")
    monkeypatch.setenv("VERIDRA_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("VERIDRA_SMTP_SENDER", "security@example.com")

    result = run_production_preflight()

    assert result.ready
    checks = {check.name: check.status for check in result.checks}
    assert checks["runtime"] is PreflightStatus.ok
    assert checks["storage"] is PreflightStatus.ok
    assert checks["legal"] is PreflightStatus.ok
    assert checks["smtp"] is PreflightStatus.ok


def test_local_preflight_allows_missing_legal_and_smtp(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("VERIDRA_ENV", "local")
    monkeypatch.setenv(
        "VERIDRA_IDENTITY_DB",
        str((tmp_path / "identity" / "veridra.sqlite3").resolve()),
    )
    monkeypatch.setenv(
        "VERIDRA_TENANT_DATA_ROOT",
        str((tmp_path / "tenants").resolve()),
    )
    monkeypatch.setenv("VERIDRA_TRUSTED_ORIGIN", "http://127.0.0.1:8010")
    monkeypatch.setenv("VERIDRA_ALLOWED_HOSTS", "127.0.0.1,localhost")
    monkeypatch.setenv("VERIDRA_BIND_HOST", "127.0.0.1")
    monkeypatch.setenv("VERIDRA_BIND_PORT", "8010")

    result = run_production_preflight()

    assert result.ready
    assert result.status is PreflightStatus.ok
    checks = {check.name: check.status for check in result.checks}
    assert checks["runtime"] is PreflightStatus.ok
    assert checks["storage"] is PreflightStatus.ok
    assert checks["legal"] is PreflightStatus.ok
    assert checks["smtp"] is PreflightStatus.ok
    assert checks["webify-billing-boundary"] is PreflightStatus.ok


def test_webify_local_agency_preflight_does_not_require_saas_providers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("VERIDRA_ENV", "local")
    monkeypatch.setenv(
        "VERIDRA_IDENTITY_DB",
        str((tmp_path / "identity" / "veridra.sqlite3").resolve()),
    )
    monkeypatch.setenv(
        "VERIDRA_TENANT_DATA_ROOT",
        str((tmp_path / "tenants").resolve()),
    )
    monkeypatch.setenv("VERIDRA_TRUSTED_ORIGIN", "http://127.0.0.1:8011")
    monkeypatch.setenv("VERIDRA_ALLOWED_HOSTS", "127.0.0.1,localhost")
    monkeypatch.setenv("VERIDRA_BIND_HOST", "127.0.0.1")
    monkeypatch.setenv("VERIDRA_BIND_PORT", "8011")

    result = run_production_preflight()

    assert result.ready
    assert result.status is PreflightStatus.ok
    checks = {check.name: check for check in result.checks}
    assert checks["runtime"].status is PreflightStatus.ok
    assert checks["storage"].status is PreflightStatus.ok
    assert checks["legal"].status is PreflightStatus.ok
    assert "not required" in checks["legal"].message
    assert checks["smtp"].status is PreflightStatus.ok
    assert "optional" in checks["smtp"].message
    assert checks["webify-billing-boundary"].status is PreflightStatus.ok
    assert "Presence Care" in checks["webify-billing-boundary"].message
