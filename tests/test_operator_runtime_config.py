from __future__ import annotations

from pathlib import Path

import pytest

from veridra.runtime_config import RuntimeConfig, RuntimeConfigurationError, RuntimeEnvironment


def _operator_env(tmp_path: Path) -> dict[str, str]:
    return {
        "VERIDRA_ENV": "operator",
        "VERIDRA_IDENTITY_DB": str((tmp_path / "identity" / "veridra.sqlite3").resolve()),
        "VERIDRA_TENANT_DATA_ROOT": str((tmp_path / "tenants").resolve()),
        "VERIDRA_TRUSTED_ORIGIN": "http://127.0.0.1:8010",
        "VERIDRA_ALLOWED_HOSTS": "127.0.0.1,localhost",
        "VERIDRA_BIND_HOST": "127.0.0.1",
        "VERIDRA_BIND_PORT": "8010",
    }


def test_operator_runtime_accepts_http_loopback(tmp_path: Path) -> None:
    config = RuntimeConfig.from_environment(_operator_env(tmp_path))

    assert config.environment is RuntimeEnvironment.operator
    assert config.bind_host == "127.0.0.1"
    assert config.trusted_origin == "http://127.0.0.1:8010"


@pytest.mark.parametrize(
    ("bind_host", "origin"),
    [
        ("0.0.0.0", "http://127.0.0.1:8010"),
        ("127.0.0.1", "http://192.168.1.10:8010"),
        ("127.0.0.1", "https://127.0.0.1:8010"),
    ],
)
def test_operator_runtime_rejects_non_loopback_or_https_shapes(
    tmp_path: Path,
    bind_host: str,
    origin: str,
) -> None:
    env = _operator_env(tmp_path)
    env["VERIDRA_BIND_HOST"] = bind_host
    env["VERIDRA_TRUSTED_ORIGIN"] = origin

    with pytest.raises(RuntimeConfigurationError):
        RuntimeConfig.from_environment(env)


def test_local_commercial_production_accepts_http_loopback(tmp_path: Path) -> None:
    env = _operator_env(tmp_path)
    env["VERIDRA_ENV"] = "production"

    config = RuntimeConfig.from_environment(env)

    assert config.environment is RuntimeEnvironment.production
    assert config.bind_host == "127.0.0.1"
    assert config.trusted_origin == "http://127.0.0.1:8010"


def test_remote_production_http_origin_is_rejected(tmp_path: Path) -> None:
    env = _operator_env(tmp_path)
    env["VERIDRA_ENV"] = "production"
    env["VERIDRA_TRUSTED_ORIGIN"] = "http://app.example.com"
    env["VERIDRA_ALLOWED_HOSTS"] = "app.example.com"

    with pytest.raises(
        RuntimeConfigurationError,
        match="requires HTTPS unless both bind and trusted origin are loopback-local",
    ):
        RuntimeConfig.from_environment(env)


def test_local_agency_requires_production_loopback(tmp_path: Path) -> None:
    env = _operator_env(tmp_path)
    env["VERIDRA_ENV"] = "production"
    env["VERIDRA_LOCAL_AGENCY"] = "1"

    config = RuntimeConfig.from_environment(env)

    assert config.local_agency is True
    assert config.environment is RuntimeEnvironment.production
    assert config.is_loopback_local is True

    wrong_environment = dict(env)
    wrong_environment["VERIDRA_ENV"] = "operator"
    with pytest.raises(RuntimeConfigurationError, match="requires VERIDRA_ENV=production"):
        RuntimeConfig.from_environment(wrong_environment)

    remote = dict(env)
    remote["VERIDRA_TRUSTED_ORIGIN"] = "https://app.example.com"
    remote["VERIDRA_ALLOWED_HOSTS"] = "app.example.com"
    remote["VERIDRA_BIND_HOST"] = "0.0.0.0"
    with pytest.raises(RuntimeConfigurationError, match="requires a loopback-only bind"):
        RuntimeConfig.from_environment(remote)
