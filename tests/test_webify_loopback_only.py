from __future__ import annotations

from pathlib import Path

import pytest

from veridra.runtime_config import RuntimeConfig, RuntimeConfigurationError


def _env(tmp_path: Path, **overrides: str) -> dict[str, str]:
    config = {
        "VERIDRA_ENV": "production",
        "VERIDRA_LOCAL_AGENCY": "1",
        "VERIDRA_IDENTITY_DB": str(tmp_path / "identity.sqlite3"),
        "VERIDRA_TENANT_DATA_ROOT": str(tmp_path / "tenants"),
        "VERIDRA_TRUSTED_ORIGIN": "http://127.0.0.1:8000",
        "VERIDRA_BIND_HOST": "127.0.0.1",
        "VERIDRA_ALLOWED_HOSTS": "127.0.0.1",
    }
    config.update(overrides)
    return config


def test_webify_production_accepts_loopback_only(tmp_path: Path) -> None:
    config = RuntimeConfig.from_environment(_env(tmp_path))
    assert config.is_loopback_local


@pytest.mark.parametrize(
    ("overrides", "description"),
    [
        ({"VERIDRA_BIND_HOST": "0.0.0.0"}, "LAN/public bind"),
        ({"VERIDRA_TRUSTED_ORIGIN": "https://example.org", "VERIDRA_ALLOWED_HOSTS": "example.org"}, "hosted origin"),
        ({"VERIDRA_TRUSTED_ORIGIN": "http://192.0.2.1:8000", "VERIDRA_ALLOWED_HOSTS": "192.0.2.1"}, "remote origin"),
    ],
)
def test_webify_production_rejects_public_hosting(
    tmp_path: Path, overrides: dict[str, str], description: str
) -> None:
    with pytest.raises(RuntimeConfigurationError, match="loopback"):
        RuntimeConfig.from_environment(_env(tmp_path, **overrides))


def test_hosted_saas_production_profile_is_retired(tmp_path: Path) -> None:
    with pytest.raises(RuntimeConfigurationError, match="Webify-only"):
        RuntimeConfig.from_environment(
            _env(tmp_path, VERIDRA_LOCAL_AGENCY="")
        )
