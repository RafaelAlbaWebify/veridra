from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse, urlunparse

from pydantic import BaseModel, ConfigDict, Field

from .core import Assessment
from .crawl import CrawlResult


class PageObservation(BaseModel):
    """Bounded, normalized facts directly observed for one crawled page."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    url: str
    status_code: int
    depth: int = Field(ge=0)
    content_type: str | None = None
    response_bytes: int = Field(ge=0)
    title: str | None = None
    meta_description: str | None = None
    h1_count: int = Field(ge=0)
    h1_text: str | None = None
    canonical_url: str | None = None
    indexable: bool | None = None
    structured_data_types: tuple[str, ...] = ()
    source_page_urls: tuple[str, ...] = ()
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class ObservationRecord(BaseModel):
    """Stable machine-comparable representation of a direct observation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str = Field(min_length=1, max_length=120)
    scope: str = Field(pattern=r"^(page|domain|assessment)$")
    subject: str
    state: str
    evidence_refs: tuple[str, ...] = ()
    observed_at: datetime | None = None
    collector_version: str | None = None
    source_type: str = "direct"
    confidence: str | None = "direct"


class ObservedAssessment(Assessment):
    """Backward-compatible assessment envelope with longitudinal crawl evidence."""

    schema_version: str = "1.4"
    collector_version: str | None = None
    crawl_profile: str | None = None
    effective_crawl_limits: dict[str, int | float] | None = None
    pages: tuple[PageObservation, ...] = ()
    observations: tuple[ObservationRecord, ...] = ()

    @classmethod
    def from_assessment(
        cls,
        assessment: Assessment,
        *,
        pages: tuple[PageObservation, ...] = (),
        observations: tuple[ObservationRecord, ...] = (),
        collector_version: str | None = None,
        crawl_profile: str | None = None,
        effective_crawl_limits: dict[str, int | float] | None = None,
    ) -> ObservedAssessment:
        normalized_observations = tuple(
            item.model_copy(
                update={
                    "observed_at": item.observed_at or assessment.generated_at,
                    "collector_version": item.collector_version or collector_version,
                }
            )
            for item in observations
        )
        return cls.model_validate(
            {
                **assessment.model_dump(mode="json"),
                "schema_version": "1.4",
                "collector_version": collector_version,
                "crawl_profile": crawl_profile,
                "effective_crawl_limits": effective_crawl_limits,
                "pages": [item.model_dump(mode="json") for item in pages],
                "observations": [
                    item.model_dump(mode="json") for item in normalized_observations
                ],
            }
        )


class _PageObservationParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title_parts: list[str] = []
        self.meta_description: str | None = None
        self.h1_parts: list[str] = []
        self.h1_count = 0
        self.canonical_href: str | None = None
        self.noindex = False
        self.structured_types: set[str] = set()
        self.links: list[str] = []
        self._in_title = False
        self._in_h1 = False
        self._json_ld_depth = 0
        self._json_ld_parts: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        data = {key.lower(): (value or "") for key, value in attrs}
        lowered = {key: value.lower() for key, value in data.items()}
        if tag == "title":
            self._in_title = True
        elif tag == "h1":
            self.h1_count += 1
            self._in_h1 = True
        elif tag == "meta" and lowered.get("name") == "description":
            value = data.get("content", "").strip()
            self.meta_description = value or None
        elif tag == "meta" and lowered.get("name") == "robots":
            self.noindex = "noindex" in lowered.get("content", "")
        elif tag == "link" and "canonical" in lowered.get("rel", ""):
            value = data.get("href", "").strip()
            self.canonical_href = value or None
        elif tag == "a" and data.get("href"):
            self.links.append(data["href"])
        elif tag == "script" and lowered.get("type") == "application/ld+json":
            self._json_ld_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        elif tag == "h1":
            self._in_h1 = False
        elif tag == "script" and self._json_ld_depth:
            self._json_ld_depth -= 1
            if self._json_ld_depth == 0:
                self._consume_json_ld()

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)
        if self._in_h1:
            self.h1_parts.append(data)
        if self._json_ld_depth:
            self._json_ld_parts.append(data)

    def _consume_json_ld(self) -> None:
        raw = "".join(self._json_ld_parts).strip()
        self._json_ld_parts.clear()
        if not raw:
            return
        try:
            value = json.loads(raw)
        except (TypeError, ValueError):
            return
        self._collect_types(value)

    def _collect_types(self, value: object) -> None:
        if isinstance(value, dict):
            raw_type = value.get("@type")
            if isinstance(raw_type, str) and raw_type.strip():
                self.structured_types.add(raw_type.strip())
            elif isinstance(raw_type, list):
                for item in raw_type:
                    if isinstance(item, str) and item.strip():
                        self.structured_types.add(item.strip())
            for child in value.values():
                self._collect_types(child)
        elif isinstance(value, list):
            for child in value:
                self._collect_types(child)


def _clean_text(parts: list[str]) -> str | None:
    value = " ".join(" ".join(parts).split())
    return value or None


def _fingerprint(
    *,
    url: str,
    status_code: int,
    content_type: str | None,
    body: str,
) -> str:
    payload = {
        "url": url,
        "status_code": status_code,
        "content_type": content_type,
        "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _crawl_identity(raw_url: str, base_url: str) -> str | None:
    parsed = urlparse(urljoin(base_url, raw_url))
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    path = parsed.path or "/"
    return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))


def page_observations(result: CrawlResult) -> tuple[PageObservation, ...]:
    parsed_pages: list[tuple[object, _PageObservationParser]] = []
    assessed_urls = {crawled.evidence.final_url for crawled in result.pages}
    inbound_sources: defaultdict[str, set[str]] = defaultdict(set)

    for crawled in result.pages:
        parser = _PageObservationParser()
        parser.feed(crawled.evidence.body)
        parsed_pages.append((crawled, parser))
        for raw_link in parser.links:
            target = _crawl_identity(raw_link, crawled.evidence.final_url)
            if target in assessed_urls and target != crawled.evidence.final_url:
                inbound_sources[target].add(crawled.evidence.final_url)

    observations: list[PageObservation] = []
    for raw_crawled, parser in parsed_pages:
        crawled = raw_crawled
        page = crawled.evidence
        content_type = page.headers.get("content-type")
        canonical_url = (
            urljoin(page.final_url, parser.canonical_href)
            if parser.canonical_href is not None
            else None
        )
        observations.append(
            PageObservation(
                url=page.final_url,
                status_code=page.status_code,
                depth=crawled.depth,
                content_type=content_type,
                response_bytes=len(page.body.encode("utf-8")),
                title=_clean_text(parser.title_parts),
                meta_description=parser.meta_description,
                h1_count=parser.h1_count,
                h1_text=_clean_text(parser.h1_parts),
                canonical_url=canonical_url,
                indexable=not parser.noindex,
                structured_data_types=tuple(sorted(parser.structured_types)),
                source_page_urls=tuple(sorted(inbound_sources[page.final_url])),
                fingerprint=_fingerprint(
                    url=page.final_url,
                    status_code=page.status_code,
                    content_type=content_type,
                    body=page.body,
                ),
            )
        )
    return tuple(sorted(observations, key=lambda item: item.url))


def observation_records(
    pages: tuple[PageObservation, ...],
) -> tuple[ObservationRecord, ...]:
    records: list[ObservationRecord] = []
    for page in pages:
        records.extend(
            (
                ObservationRecord(
                    key="page.http-status",
                    scope="page",
                    subject=page.url,
                    state=str(page.status_code),
                ),
                ObservationRecord(
                    key="page.fingerprint",
                    scope="page",
                    subject=page.url,
                    state=page.fingerprint,
                ),
                ObservationRecord(
                    key="page.indexable",
                    scope="page",
                    subject=page.url,
                    state=(
                        "unknown"
                        if page.indexable is None
                        else str(page.indexable).lower()
                    ),
                ),
                ObservationRecord(
                    key="page.source-pages",
                    scope="page",
                    subject=page.url,
                    state=json.dumps(
                        list(page.source_page_urls),
                        separators=(",", ":"),
                        ensure_ascii=False,
                    ),
                ),
            )
        )
    return tuple(sorted(records, key=lambda item: (item.subject, item.key, item.state)))
