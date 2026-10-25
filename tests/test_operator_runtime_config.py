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


def test_legacy_production_alias_is_retired(tmp_path: Path) -> None:
    env = _operator_env(tmp_path)
    env["VERIDRA_ENV"] = "production"
    env["VERIDRA_LOCAL_AGENCY"] = "1"
    with pytest.raises(RuntimeConfigurationError, match="production is retired"):
        RuntimeConfig.from_environment(env)


def test_remote_production_http_origin_is_rejected(tmp_path: Path) -> None:
    env = _operator_env(tmp_path)
    env["VERIDRA_ENV"] = "production"
    env["VERIDRA_TRUSTED_ORIGIN"] = "http://app.example.com"
    env["VERIDRA_ALLOWED_HOSTS"] = "app.example.com"

    with pytest.raises(
        RuntimeConfigurationError,
        match="production is retired",
    ):
        RuntimeConfig.from_environment(env)


def test_legacy_flag_is_not_an_alternative_to_local(tmp_path: Path) -> None:
    env = _operator_env(tmp_path)
    env["VERIDRA_ENV"] = "operator"
    env["VERIDRA_LOCAL_AGENCY"] = "1"
    with pytest.raises(RuntimeConfigurationError):
        RuntimeConfig.from_environment(env)


def test_canonical_local_runtime_requires_no_legacy_agency_flag(tmp_path: Path) -> None:
    env = _operator_env(tmp_path)
    env["VERIDRA_ENV"] = "local"
    env.pop("VERIDRA_LOCAL_AGENCY", None)

    config = RuntimeConfig.from_environment(env)

    assert config.environment is RuntimeEnvironment.local
    assert config.local_agency is True
    assert config.is_loopback_local is True

    remote = dict(env)
    remote["VERIDRA_BIND_HOST"] = "0.0.0.0"
    with pytest.raises(RuntimeConfigurationError, match="loopback"):
        RuntimeConfig.from_environment(remote)


def test_private_runtime_flags_distinguish_canonical_and_compatibility_modes(
    tmp_path: Path,
) -> None:
    env = _operator_env(tmp_path)

    operator = RuntimeConfig.from_environment(env)
    assert operator.is_private_webify is True
    assert operator.is_legacy_operator is True

    env["VERIDRA_ENV"] = "local"
    local = RuntimeConfig.from_environment(env)
    assert local.is_private_webify is True
    assert local.is_legacy_operator is False
    assert local.local_agency is True

    env["VERIDRA_ENV"] = "production"
    env["VERIDRA_LOCAL_AGENCY"] = "1"
    with pytest.raises(RuntimeConfigurationError, match="production is retired"):
        RuntimeConfig.from_environment(env)
