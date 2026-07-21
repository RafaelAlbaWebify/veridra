from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

_HEX_COLOUR = re.compile(r"^#[0-9A-Fa-f]{6}$")


class ReportProfile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    organisation_name: str = Field(default="Veridra", min_length=1, max_length=120)
    client_name: str | None = Field(default=None, max_length=120)
    consultant_name: str | None = Field(default=None, max_length=120)
    accent_colour: str = "#22272d"
    introduction: str | None = Field(default=None, max_length=1200)
    call_to_action_label: str | None = Field(default=None, max_length=80)
    call_to_action_url: str | None = Field(default=None, max_length=2048)
    language: str = "en"
    show_raw_evidence: bool = True

    @field_validator("accent_colour")
    @classmethod
    def validate_accent_colour(cls, value: str) -> str:
        if not _HEX_COLOUR.fullmatch(value):
            raise ValueError("Accent colour must be a six-digit hexadecimal colour.")
        return value.lower()

    @field_validator("language")
    @classmethod
    def validate_language(cls, value: str) -> str:
        lowered = value.lower()
        if lowered not in {"en", "es"}:
            raise ValueError("Report language must be 'en' or 'es'.")
        return lowered

    @field_validator("call_to_action_url")
    @classmethod
    def validate_call_to_action_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.startswith(("https://", "http://")):
            raise ValueError("Call-to-action URL must use HTTP or HTTPS.")
        return value


DEFAULT_REPORT_PROFILE = ReportProfile()
