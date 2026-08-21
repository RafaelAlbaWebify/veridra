from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlparse

from fastapi import FastAPI

from .runtime_config import RuntimeConfig, RuntimeConfigurationError, RuntimeEnvironment


@dataclass(frozen=True)
class LegalLinks:
    privacy_url: str
    terms_url: str

    @staticmethod
    def _https_url(value: str, *, name: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise RuntimeConfigurationError(f"{name} must be an HTTPS URL.")
        return value

    @classmethod
    def from_environment(cls, env: Mapping[str, str] | None = None) -> LegalLinks | None:
        values = os.environ if env is None else env
        privacy = values.get("VERIDRA_PRIVACY_URL", "").strip()
        terms = values.get("VERIDRA_TERMS_URL", "").strip()
        if not privacy and not terms:
            return None
        if not privacy or not terms:
            raise RuntimeConfigurationError(
                "VERIDRA_PRIVACY_URL and VERIDRA_TERMS_URL must be configured together."
            )
        return cls(
            privacy_url=cls._https_url(privacy, name="VERIDRA_PRIVACY_URL"),
            terms_url=cls._https_url(terms, name="VERIDRA_TERMS_URL"),
        )


def configure_runtime_legal(app: FastAPI, runtime: RuntimeConfig) -> None:
    links = LegalLinks.from_environment()
    if runtime.environment is RuntimeEnvironment.production and links is None:
        raise RuntimeConfigurationError(
            "VERIDRA_PRIVACY_URL and VERIDRA_TERMS_URL are required in production."
        )
    if links is not None:
        app.state.veridra_legal_links = links
