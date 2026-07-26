from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Mapping
from urllib.parse import urlparse


class RuntimeConfigurationError(RuntimeError):
    pass


class RuntimeEnvironment(StrEnum):
    development = "development"
    test = "test"
    production = "production"


def _absolute_path(value: str, *, name: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise RuntimeConfigurationError(f"{name} must be an absolute path.")
    return path.resolve()


def _split_hosts(value: str) -> tuple[str, ...]:
    hosts = tuple(part.strip().lower() for part in value.split(",") if part.strip())
    if any(host == "*" for host in hosts):
        raise RuntimeConfigurationError("VERIDRA_ALLOWED_HOSTS cannot contain a wildcard.")
    return hosts


@dataclass(frozen=True)
class RuntimeConfig:
    environment: RuntimeEnvironment
    identity_database: Path | None
    tenant_data_root: Path | None
    trusted_origin: str | None
    allowed_hosts: tuple[str, ...]
    bind_host: str
    bind_port: int

    @classmethod
    def from_environment(cls, env: Mapping[str, str] | None = None) -> RuntimeConfig:
        values = os.environ if env is None else env
        try:
            environment = RuntimeEnvironment(values.get("VERIDRA_ENV", "development").strip())
        except ValueError as exc:
            raise RuntimeConfigurationError("VERIDRA_ENV is invalid.") from exc

        identity_value = values.get("VERIDRA_IDENTITY_DB", "").strip()
        tenant_value = values.get("VERIDRA_TENANT_DATA_ROOT", "").strip()
        origin = values.get("VERIDRA_TRUSTED_ORIGIN", "").strip() or None
        hosts = _split_hosts(values.get("VERIDRA_ALLOWED_HOSTS", ""))
        bind_host = values.get("VERIDRA_BIND_HOST", "127.0.0.1").strip()
        try:
            bind_port = int(values.get("VERIDRA_BIND_PORT", "8000"))
        except ValueError as exc:
            raise RuntimeConfigurationError("VERIDRA_BIND_PORT is invalid.") from exc
        if not 1 <= bind_port <= 65535:
            raise RuntimeConfigurationError("VERIDRA_BIND_PORT must be between 1 and 65535.")
        try:
            ipaddress.ip_address(bind_host)
        except ValueError as exc:
            raise RuntimeConfigurationError("VERIDRA_BIND_HOST must be an IP address.") from exc

        identity = _absolute_path(identity_value, name="VERIDRA_IDENTITY_DB") if identity_value else None
        tenant_root = (
            _absolute_path(tenant_value, name="VERIDRA_TENANT_DATA_ROOT")
            if tenant_value
            else None
        )
        config = cls(
            environment=environment,
            identity_database=identity,
            tenant_data_root=tenant_root,
            trusted_origin=origin,
            allowed_hosts=hosts,
            bind_host=bind_host,
            bind_port=bind_port,
        )
        config.validate()
        return config

    def validate(self) -> None:
        if self.environment is not RuntimeEnvironment.production:
            return
        if self.identity_database is None:
            raise RuntimeConfigurationError("VERIDRA_IDENTITY_DB is required in production.")
        if self.tenant_data_root is None:
            raise RuntimeConfigurationError(
                "VERIDRA_TENANT_DATA_ROOT is required in production."
            )
        if self.trusted_origin is None:
            raise RuntimeConfigurationError("VERIDRA_TRUSTED_ORIGIN is required in production.")
        parsed = urlparse(self.trusted_origin)
        if parsed.scheme != "https" or not parsed.hostname or parsed.path not in {"", "/"}:
            raise RuntimeConfigurationError(
                "VERIDRA_TRUSTED_ORIGIN must be an HTTPS origin without a path."
            )
        if not self.allowed_hosts:
            raise RuntimeConfigurationError("VERIDRA_ALLOWED_HOSTS is required in production.")
        if parsed.hostname.lower() not in self.allowed_hosts:
            raise RuntimeConfigurationError(
                "VERIDRA_ALLOWED_HOSTS must include the trusted-origin host."
            )

    def configure_directories(self) -> None:
        if self.identity_database is not None:
            self.identity_database.parent.mkdir(parents=True, exist_ok=True)
        if self.tenant_data_root is not None:
            self.tenant_data_root.mkdir(parents=True, exist_ok=True)
