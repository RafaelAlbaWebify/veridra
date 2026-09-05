from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html.parser import HTMLParser

from .core import Finding, Status
from .crawl import CrawlResult

_MAX_EXAMPLES = 20
_MONTHS = {
    name.lower(): index
    for index, name in enumerate(
        (
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ),
        start=1,
    )
}
_DAY_NAMES = {
    "mon": "monday",
    "monday": "monday",
    "tue": "tuesday",
    "tues": "tuesday",
    "tuesday": "tuesday",
    "wed": "wednesday",
    "wednesday": "wednesday",
    "thu": "thursday",
    "thur": "thursday",
    "thurs": "thursday",
    "thursday": "thursday",
    "fri": "friday",
    "friday": "friday",
    "sat": "saturday",
    "saturday": "saturday",
    "sun": "sunday",
    "sunday": "sunday",
}
_PLACEHOLDER_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "wordpress_sample_page",
        re.compile(
            r"\bthis is an example page\b.{0,220}\bdifferent from a blog post\b",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "literal_phone_placeholder",
        re.compile(
            r"\b(?:call|phone|telephone|tel)\s*(?:[:\-–]\s*)?"
            r"(?:\[|\{)?phone number(?:\]|\})?\b",
            re.IGNORECASE,
        ),
    ),
)
_UPDATED_RE = re.compile(
    r"\b(?:last\s+updated|updated)\s*(?::|on)?\s*"
    r"(january|february|march|april|may|june|july|august|september|october|november|december)"
    r"\s+(20\d{2})\b",
    re.IGNORECASE,
)
_DAY_TIME_RE = re.compile(
    r"\b(mon(?:day)?|tue(?:s|sday)?|wed(?:nesday)?|thu(?:r|rs|rsday)?|fri(?:day)?|"
    r"sat(?:urday)?|sun(?:day)?)\b"
    r"[^\n\r;|]{0,45}?"
    r"(closed|(?:\d{1,2}(?::\d{2})?\s*(?:am|pm)?\s*[-–]\s*"
    r"\d{1,2}(?::\d{2})?\s*(?:am|pm)?))",
    re.IGNORECASE,
)


@dataclass
class _TextSignals:
    text_parts: list[str] = field(default_factory=list)
    title_parts: list[str] = field(default_factory=list)
    _in_title: bool = False


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.signals = _TextSignals()
        self._suppressed_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        lowered = tag.lower()
        if lowered in {"script", "style", "noscript"}:
            self._suppressed_depth += 1
        if lowered == "title":
            self.signals._in_title = True

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered in {"script", "style", "noscript"} and self._suppressed_depth:
            self._suppressed_depth -= 1
        if lowered == "title":
            self.signals._in_title = False

    def handle_data(self, data: str) -> None:
        if self._suppressed_depth:
            return
        normalized = " ".join(data.split())
        if not normalized:
            return
        self.signals.text_parts.append(normalized)
        if self.signals._in_title:
            self.signals.title_parts.append(normalized)


def _visible_text(body: str) -> str:
    parser = _VisibleTextParser()
    parser.feed(body)
    parser.close()
    return "\n".join(parser.signals.text_parts)


def _normalized_time_value(value: str) -> str:
    normalized = value.casefold().replace("–", "-")
    return re.sub(r"\s+", "", normalized)


def _opening_hours(text: str) -> dict[str, str]:
    schedule: dict[str, str] = {}
    for match in _DAY_TIME_RE.finditer(text):
        raw_day = match.group(1).casefold()
        day = _DAY_NAMES.get(raw_day)
        if day is None:
            continue
        schedule[day] = _normalized_time_value(match.group(2))
    return schedule


def _months_old(year: int, month: int, reference: datetime) -> int:
    return (reference.year - year) * 12 + reference.month - month


def _placeholder_finding(result: CrawlResult) -> Finding:
    affected: list[dict[str, str]] = []
    for crawled in result.pages:
        text = _visible_text(crawled.evidence.body)
        for kind, pattern in _PLACEHOLDER_PATTERNS:
            match = pattern.search(text)
            if match is None:
                continue
            affected.append(
                {
                    "url": crawled.evidence.final_url,
                    "pattern": kind,
                    "example": " ".join(match.group(0).split())[:240],
                }
            )
            break
    return Finding(
        id="content.placeholder-default",
        area="Trust and content quality",
        title="Default or placeholder public content",
        status=Status.attention if affected else Status.passed,
        severity="medium" if affected else "info",
        summary=(
            f"{len(affected)} crawled pages contain a deterministic default/placeholder pattern."
            if affected
            else (
                "No configured default/placeholder content pattern was observed "
                "in the bounded crawl."
            )
        ),
        recommendation=(
            "Replace confirmed default or placeholder public copy with accurate business content."
            if affected
            else None
        ),
        evidence={
            "affected_pages": affected[:_MAX_EXAMPLES],
            "bounded_examples": _MAX_EXAMPLES,
        },
    )


def _staleness_finding(result: CrawlResult, reference: datetime) -> Finding:
    indicators: list[dict[str, object]] = []
    for crawled in result.pages:
        text = _visible_text(crawled.evidence.body)
        for match in _UPDATED_RE.finditer(text):
            month = _MONTHS[match.group(1).casefold()]
            year = int(match.group(2))
            age_months = _months_old(year, month, reference)
            if age_months < 18:
                continue
            indicators.append(
                {
                    "url": crawled.evidence.final_url,
                    "observed_label": " ".join(match.group(0).split()),
                    "age_months_at_assessment": age_months,
                }
            )
    return Finding(
        id="content.explicit-update-age",
        area="Trust and content quality",
        title="Explicit content-update age indicator",
        status=Status.attention if indicators else Status.passed,
        severity="low" if indicators else "info",
        summary=(
            (
                f"{len(indicators)} crawled pages explicitly label content as last "
                "updated at least 18 months ago. This is an age indicator, not proof "
                "that the content is incorrect."
            )
            if indicators
            else (
                "No explicit content-update label at least 18 months old was observed "
                "in the bounded crawl."
            )
        ),
        recommendation=(
            (
                "Confirm whether the dated content is still accurate; refresh the public "
                "update label only when the content is actually reviewed."
            )
            if indicators
            else None
        ),
        evidence={
            "indicators": indicators[:_MAX_EXAMPLES],
            "threshold_months": 18,
            "assessment_reference": reference.date().isoformat(),
            "copyright_years_excluded": True,
        },
    )


def _hours_consistency_finding(result: CrawlResult) -> Finding:
    schedules: list[tuple[str, dict[str, str]]] = []
    for crawled in result.pages:
        schedule = _opening_hours(_visible_text(crawled.evidence.body))
        if schedule:
            schedules.append((crawled.evidence.final_url, schedule))

    conflicts: list[dict[str, object]] = []
    for index, (left_url, left) in enumerate(schedules):
        for right_url, right in schedules[index + 1 :]:
            overlap = sorted(set(left) & set(right))
            differences = [
                {
                    "day": day,
                    "first_value": left[day],
                    "second_value": right[day],
                }
                for day in overlap
                if left[day] != right[day]
            ]
            if not differences:
                continue
            conflicts.append(
                {
                    "first_url": left_url,
                    "second_url": right_url,
                    "differences": differences,
                }
            )

    return Finding(
        id="content.opening-hours-consistency",
        area="Local presence",
        title="Cross-page opening-hours consistency",
        status=Status.attention if conflicts else Status.passed,
        severity="high" if conflicts else "info",
        summary=(
            (
                f"{len(conflicts)} crawled page pairs publish conflicting hours for at "
                "least one matching weekday."
            )
            if conflicts
            else (
                "No contradictory weekday opening-hour values were observed across "
                "the bounded crawl."
            )
        ),
        recommendation=(
            (
                "Confirm the authoritative business hours with the owner, then make "
                "customer-facing pages consistent."
            )
            if conflicts
            else None
        ),
        evidence={
            "conflicts": conflicts[:_MAX_EXAMPLES],
            "pages_with_detected_weekday_hours": len(schedules),
            "owner_confirmation_required_before_change": True,
        },
    )


def analyze_business_content_consistency(
    result: CrawlResult,
    *,
    reference: datetime | None = None,
) -> list[Finding]:
    now = reference or datetime.now(UTC)
    return [
        _placeholder_finding(result),
        _staleness_finding(result, now),
        _hours_consistency_finding(result),
    ]
