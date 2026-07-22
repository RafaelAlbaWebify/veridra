from __future__ import annotations

import base64
import binascii
import re
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_HEX_COLOUR = re.compile(r"^#[0-9A-Fa-f]{6}$")
_DATA_IMAGE = re.compile(r"^data:image/(png|jpeg);base64,([A-Za-z0-9+/=]+)$")
_MAX_LOGO_BYTES = 200_000
_MAX_PROFILE_TEXT = 8_000

REPORT_SECTIONS = (
    "executive_summary",
    "priority_actions",
    "business_impact",
    "implementation_roadmap",
    "assessment_areas",
    "findings",
    "conclusion",
    "call_to_action",
)


class ReportProfile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    allowed_sections: ClassVar[tuple[str, ...]] = REPORT_SECTIONS

    organisation_name: str = Field(default="Veridra", min_length=1, max_length=120)
    client_name: str | None = Field(default=None, max_length=120)
    consultant_name: str | None = Field(default=None, max_length=120)
    agency_email: str | None = Field(default=None, max_length=254)
    agency_phone: str | None = Field(default=None, max_length=80)
    agency_website: str | None = Field(default=None, max_length=2048)
    accent_colour: str = "#22272d"
    cover_title: str | None = Field(default=None, max_length=180)
    introduction: str | None = Field(default=None, max_length=1200)
    executive_summary: str | None = Field(default=None, max_length=2000)
    conclusion: str | None = Field(default=None, max_length=2000)
    call_to_action_label: str | None = Field(default=None, max_length=80)
    call_to_action_url: str | None = Field(default=None, max_length=2048)
    language: str = "en"
    show_raw_evidence: bool = True
    selected_areas: tuple[str, ...] = ()
    section_order: tuple[str, ...] = REPORT_SECTIONS
    logo_data_uri: str | None = None

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

    @field_validator("call_to_action_url", "agency_website")
    @classmethod
    def validate_public_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.startswith(("https://", "http://")):
            raise ValueError("Report URLs must use HTTP or HTTPS.")
        return value

    @field_validator("selected_areas")
    @classmethod
    def validate_selected_areas(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        cleaned = tuple(dict.fromkeys(value.strip() for value in values if value.strip()))
        if len(cleaned) > 20:
            raise ValueError("A report profile may select at most 20 assessment areas.")
        return cleaned

    @field_validator("section_order")
    @classmethod
    def validate_section_order(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if not values:
            raise ValueError("At least one report section is required.")
        if len(values) != len(set(values)):
            raise ValueError("Report sections must be unique.")
        unknown = set(values) - set(REPORT_SECTIONS)
        if unknown:
            raise ValueError("Unsupported report section.")
        return values

    @field_validator("logo_data_uri")
    @classmethod
    def validate_logo(cls, value: str | None) -> str | None:
        if value is None:
            return None
        match = _DATA_IMAGE.fullmatch(value)
        if match is None:
            raise ValueError("Logo must be an embedded PNG or JPEG data URI.")
        try:
            decoded = base64.b64decode(match.group(2), validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("Logo data is not valid base64.") from exc
        if not decoded or len(decoded) > _MAX_LOGO_BYTES:
            raise ValueError("Embedded logo must be between 1 byte and 200 KB.")
        if match.group(1) == "png" and not decoded.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("Embedded PNG signature is invalid.")
        if match.group(1) == "jpeg" and not decoded.startswith(b"\xff\xd8\xff"):
            raise ValueError("Embedded JPEG signature is invalid.")
        return value

    @model_validator(mode="after")
    def validate_profile_size(self) -> ReportProfile:
        text_size = sum(
            len(value or "")
            for value in (
                self.organisation_name,
                self.client_name,
                self.consultant_name,
                self.agency_email,
                self.agency_phone,
                self.agency_website,
                self.cover_title,
                self.introduction,
                self.executive_summary,
                self.conclusion,
                self.call_to_action_label,
                self.call_to_action_url,
            )
        )
        if text_size > _MAX_PROFILE_TEXT:
            raise ValueError("Report profile text exceeds the supported size.")
        return self


DEFAULT_REPORT_PROFILE = ReportProfile()
