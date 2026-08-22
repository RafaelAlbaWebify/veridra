from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from .prospect import Prospect, ProspectStatus


class Territory(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=160)
    country_code: str = Field(min_length=2, max_length=2)
    administrative_area: str = Field(default="", max_length=160)
    locality: str = Field(default="", max_length=160)


class QueryTemplate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=160)
    sector: str = Field(min_length=1, max_length=120)
    phrases: tuple[str, ...] = Field(min_length=1, max_length=100)
    countries: tuple[str, ...] = Field(default=(), max_length=100)


class ObservedBusiness(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    provider: str = Field(min_length=1, max_length=80)
    provider_key: str = Field(min_length=1, max_length=240)
    name: str = Field(min_length=1, max_length=200)
    category: str = Field(default="", max_length=120)
    locality: str = Field(default="", max_length=120)
    administrative_area: str = Field(default="", max_length=120)
    country_code: str = Field(min_length=2, max_length=2)
    postal_area: str = Field(default="", max_length=40)
    website: HttpUrl | None = None
    phone: str = Field(default="", max_length=80)
    source_url: HttpUrl | None = None
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class PreparedQuery:
    sequence: int
    phrase: str
    query_text: str


@dataclass(frozen=True, slots=True)
class SearchRequest:
    territory_name: str
    country_code: str
    phrase: str
    max_results: int = 20

    def __post_init__(self) -> None:
        if not self.territory_name.strip():
            raise ValueError("territory_name cannot be blank.")
        if len(self.country_code.strip()) != 2:
            raise ValueError("country_code must contain exactly two characters.")
        if not self.phrase.strip():
            raise ValueError("phrase cannot be blank.")
        if self.max_results < 1 or self.max_results > 200:
            raise ValueError("max_results must be between 1 and 200.")


class DiscoveryProvider(Protocol):
    async def capture_candidates(self, request: SearchRequest) -> Sequence[ObservedBusiness]: ...


def normalize_business_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold().strip()
    normalized = re.sub(r"[^\w\s]", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def build_prepared_queries(
    *,
    phrases: Sequence[str],
    territory_name: str,
    country_code: str,
) -> tuple[PreparedQuery, ...]:
    clean_territory = territory_name.strip()
    clean_country = country_code.strip().upper()
    if not clean_territory:
        raise ValueError("territory_name cannot be blank.")
    if len(clean_country) != 2:
        raise ValueError("country_code must contain exactly two characters.")

    prepared: list[PreparedQuery] = []
    seen_phrases: set[str] = set()
    for raw_phrase in phrases:
        phrase = raw_phrase.strip()
        folded = phrase.casefold()
        if not phrase or folded in seen_phrases:
            continue
        seen_phrases.add(folded)
        prepared.append(
            PreparedQuery(
                sequence=len(prepared) + 1,
                phrase=phrase,
                query_text=f"{phrase} in {clean_territory}, {clean_country}",
            )
        )
    if not prepared:
        raise ValueError("At least one non-empty query phrase is required.")
    return tuple(prepared)


def deduplicate_observations(
    observations: Sequence[ObservedBusiness],
) -> list[ObservedBusiness]:
    seen: set[tuple[str, str]] = set()
    unique: list[ObservedBusiness] = []
    for observation in observations:
        identity = (observation.provider.casefold(), observation.provider_key.casefold())
        if identity in seen:
            continue
        seen.add(identity)
        unique.append(observation)
    return unique


def prospect_from_observation(observation: ObservedBusiness) -> Prospect:
    source = str(observation.source_url) if observation.source_url is not None else ""
    evidence = (
        f"Observed via {observation.provider} at {observation.observed_at.isoformat()}."
        + (f" Source: {source}" if source else "")
    )
    return Prospect.model_validate(
        {
            "business_name": observation.name,
            "website": str(observation.website) if observation.website is not None else None,
            "sector": observation.category,
            "locality": observation.locality,
            "administrative_area": observation.administrative_area,
            "country_code": observation.country_code.upper(),
            "phone": observation.phone,
            "provider": observation.provider,
            "provider_key": observation.provider_key,
            "source_url": source or None,
            "evidence_summary": evidence,
            "status": ProspectStatus.needs_review,
            "created_at": observation.observed_at,
            "updated_at": observation.observed_at,
        }
    )


def prospects_from_observations(
    observations: Sequence[ObservedBusiness],
) -> list[Prospect]:
    return [prospect_from_observation(item) for item in deduplicate_observations(observations)]


class FixtureDiscoveryProvider:
    def __init__(self, fixture_path: Path) -> None:
        self.fixture_path = fixture_path

    async def capture_candidates(self, request: SearchRequest) -> Sequence[ObservedBusiness]:
        raw = json.loads(self.fixture_path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError("Discovery fixture must contain a list of records.")
        records: list[ObservedBusiness] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            matched = item.get("matched_phrases", [])
            country = item.get("country_code", "")
            if not isinstance(matched, list) or request.phrase.casefold() not in {
                str(value).casefold() for value in matched
            }:
                continue
            if str(country).upper() != request.country_code.upper():
                continue
            records.append(ObservedBusiness.model_validate(item))
            if len(records) >= request.max_results:
                break
        return records
