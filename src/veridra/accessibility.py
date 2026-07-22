from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from html.parser import HTMLParser

from .core import Finding, Status
from .crawl import CrawlResult

_MAX_EXAMPLES = 20


@dataclass
class _Signals:
    language: str = ""
    viewport: bool = False
    ids: list[str] = field(default_factory=list)
    headings: list[int] = field(default_factory=list)
    images: int = 0
    images_missing_alt: int = 0
    controls: int = 0
    controls_unlabelled: int = 0
    empty_links: int = 0
    empty_buttons: int = 0


class _AccessibilityParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.signals = _Signals()
        self._labels_for: set[str] = set()
        self._control_ids: list[tuple[str, bool]] = []
        self._interactive: list[tuple[str, bool]] = []
        self._stack: list[tuple[str, int | None]] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        data = {key.lower(): (value or "") for key, value in attrs}
        lowered = tag.lower()
        element_id = data.get("id", "").strip()
        if element_id:
            self.signals.ids.append(element_id)
        if lowered == "html":
            self.signals.language = data.get("lang", "").strip()
        if lowered == "meta" and data.get("name", "").lower() == "viewport":
            self.signals.viewport = bool(data.get("content", "").strip())
        if lowered == "label" and data.get("for", "").strip():
            self._labels_for.add(data["for"].strip())
        if lowered == "img":
            self.signals.images += 1
            if "alt" not in data:
                self.signals.images_missing_alt += 1
        if lowered in {"input", "select", "textarea"}:
            input_type = data.get("type", "").lower()
            if input_type != "hidden":
                self.signals.controls += 1
                named = bool(
                    data.get("aria-label", "").strip()
                    or data.get("aria-labelledby", "").strip()
                    or data.get("title", "").strip()
                )
                self._control_ids.append((element_id, named))
        if lowered in {"a", "button"}:
            named = bool(
                data.get("aria-label", "").strip()
                or data.get("aria-labelledby", "").strip()
                or data.get("title", "").strip()
            )
            self._interactive.append((lowered, named))
            self._stack.append((lowered, len(self._interactive) - 1))
        else:
            self._stack.append((lowered, None))
        if len(lowered) == 2 and lowered.startswith("h") and lowered[1].isdigit():
            level = int(lowered[1])
            if 1 <= level <= 6:
                self.signals.headings.append(level)

    def handle_startendtag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        self.handle_starttag(tag, attrs)
        if self._stack:
            self._stack.pop()

    def handle_data(self, data: str) -> None:
        if not data.strip():
            return
        for _, index in reversed(self._stack):
            if index is not None:
                tag, _ = self._interactive[index]
                self._interactive[index] = (tag, True)
                break

    def handle_endtag(self, tag: str) -> None:
        if self._stack:
            self._stack.pop()

    def close(self) -> None:
        super().close()
        self.signals.controls_unlabelled = sum(
            not named and (not control_id or control_id not in self._labels_for)
            for control_id, named in self._control_ids
        )
        self.signals.empty_links = sum(
            tag == "a" and not named for tag, named in self._interactive
        )
        self.signals.empty_buttons = sum(
            tag == "button" and not named for tag, named in self._interactive
        )


def _affected(
    result: CrawlResult,
    predicate: Callable[[_Signals], bool],
) -> list[str]:
    urls: list[str] = []
    for crawled in result.pages:
        parser = _AccessibilityParser()
        parser.feed(crawled.evidence.body)
        parser.close()
        if predicate(parser.signals):
            urls.append(crawled.evidence.final_url)
    return urls[:_MAX_EXAMPLES]


def _finding(
    identifier: str,
    title: str,
    summary: str,
    recommendation: str,
    affected_urls: list[str],
    *,
    severity: str = "medium",
) -> Finding:
    return Finding(
        id=identifier,
        area="Accessibility",
        title=title,
        status=Status.attention if affected_urls else Status.passed,
        severity=severity if affected_urls else "info",
        summary=summary.format(count=len(affected_urls)),
        recommendation=recommendation if affected_urls else None,
        evidence={"affected_urls": affected_urls, "bounded_examples": _MAX_EXAMPLES},
    )


def analyze_accessibility(result: CrawlResult) -> list[Finding]:
    missing_language = _affected(result, lambda item: not item.language)
    missing_viewport = _affected(result, lambda item: not item.viewport)
    unlabelled_controls = _affected(result, lambda item: item.controls_unlabelled > 0)
    empty_interactive = _affected(
        result,
        lambda item: item.empty_links > 0 or item.empty_buttons > 0,
    )
    missing_alt = _affected(result, lambda item: item.images_missing_alt > 0)
    heading_skips = _affected(
        result,
        lambda item: any(
            current > previous + 1
            for previous, current in zip(item.headings, item.headings[1:])
        ),
    )
    duplicate_ids = _affected(
        result,
        lambda item: any(count > 1 for count in Counter(item.ids).values()),
    )
    return [
        _finding(
            "accessibility.document-language",
            "Document language declaration",
            "{count} crawled pages do not declare an HTML language.",
            "Add a valid lang attribute to the root HTML element.",
            missing_language,
        ),
        _finding(
            "accessibility.viewport",
            "Responsive viewport declaration",
            "{count} crawled pages do not expose a viewport meta declaration.",
            "Add an appropriate viewport meta declaration for responsive presentation.",
            missing_viewport,
            severity="low",
        ),
        _finding(
            "accessibility.form-labels",
            "Detectable form labels",
            "{count} crawled pages contain form controls without a detectable label.",
            "Associate visible labels or accessible names with every non-hidden form control.",
            unlabelled_controls,
            severity="high",
        ),
        _finding(
            "accessibility.interactive-names",
            "Accessible link and button names",
            "{count} crawled pages contain links or buttons without detectable names.",
            "Provide visible text or an appropriate accessible name for each interactive control.",
            empty_interactive,
            severity="high",
        ),
        _finding(
            "accessibility.image-alt",
            "Image alternative-text coverage",
            "{count} crawled pages contain images missing an alt attribute.",
            "Add meaningful alt text, or explicit empty alt text for decorative images.",
            missing_alt,
        ),
        _finding(
            "accessibility.heading-order",
            "Heading-order continuity",
            "{count} crawled pages contain a detected heading-level skip.",
            "Review heading hierarchy so levels communicate a coherent document outline.",
            heading_skips,
            severity="low",
        ),
        _finding(
            "accessibility.duplicate-ids",
            "Unique element identifiers",
            "{count} crawled pages contain duplicate non-empty element IDs.",
            "Make element IDs unique within each document.",
            duplicate_ids,
        ),
    ]
