from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from veridra.core import Assessment, Finding, Status
from veridra.history import HistoryStore
from veridra.observations import ObservedAssessment, PageObservation


def _finding() -> Finding:
    return Finding(
        id="health.title",
        area="Website health",
        title="Title",
        status=Status.passed,
        severity="info",
        summary="Present.",
    )


def _page(
    url: str,
    fingerprint: str,
    *,
    status_code: int = 200,
) -> PageObservation:
    return PageObservation(
        url=url,
        status_code=status_code,
        depth=0,
        content_type="text/html",
        response_bytes=100,
        title="Example",
        h1_count=1,
        h1_text="Example",
        indexable=True,
        fingerprint=fingerprint,
    )


def _observed(
    generated_at: datetime,
    pages: tuple[PageObservation, ...],
) -> ObservedAssessment:
    base = Assessment.build(
        "https://example.com",
        [_finding()],
        generated_at=generated_at,
    )
    return ObservedAssessment.from_assessment(
        base,
        pages=pages,
        collector_version="test",
        crawl_profile="quick",
        effective_crawl_limits={"max_pages": 10, "max_depth": 1},
    )


def test_history_round_trip_preserves_observation_envelope(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path)
    assessment = _observed(
        datetime(2026, 9, 1, tzinfo=UTC),
        (_page("https://example.com/", "a" * 64),),
    )

    entry_id = store.save(assessment)
    loaded = store.load(entry_id)

    assert isinstance(loaded, ObservedAssessment)
    assert loaded.schema_version == "1.4"
    assert loaded.collector_version == "test"
    assert loaded.crawl_profile == "quick"
    assert loaded.pages == assessment.pages


def test_old_assessment_json_preserves_legacy_type_and_unknown_history(
    tmp_path: Path,
) -> None:
    store = HistoryStore(tmp_path)
    legacy = Assessment.build(
        "https://example.com",
        [_finding()],
        generated_at=datetime(2026, 8, 1, tzinfo=UTC),
    )
    entry_id = store.save(legacy)

    loaded = store.load(entry_id)

    assert type(loaded) is Assessment
    assert loaded == legacy
    assert loaded.schema_version == "1.3"
    assert not hasattr(loaded, "collector_version")
    assert not hasattr(loaded, "pages")


def test_compare_derives_exact_page_inventory_deltas(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path)
    before = _observed(
        datetime(2026, 9, 1, tzinfo=UTC),
        (
            _page("https://example.com/", "a" * 64),
            _page("https://example.com/removed", "b" * 64),
            _page("https://example.com/status", "c" * 64, status_code=200),
        ),
    )
    after = _observed(
        datetime(2026, 9, 2, tzinfo=UTC),
        (
            _page("https://example.com/", "d" * 64),
            _page("https://example.com/added", "e" * 64),
            _page("https://example.com/status", "f" * 64, status_code=404),
        ),
    )

    comparison = store.compare(store.save(before), store.save(after))

    assert comparison.page_history_available is True
    assert comparison.pages_added == ("https://example.com/added",)
    assert comparison.pages_removed == ("https://example.com/removed",)
    assert comparison.pages_changed == (
        "https://example.com/",
        "https://example.com/status",
    )
    assert comparison.page_status_changed == ("https://example.com/status",)
    assert comparison.added == ()
    assert comparison.resolved == ()
    assert comparison.changed == ()
    assert comparison.unchanged == ("health.title",)


def test_legacy_to_observed_comparison_does_not_invent_page_history(
    tmp_path: Path,
) -> None:
    store = HistoryStore(tmp_path)
    legacy = Assessment.build(
        "https://example.com",
        [_finding()],
        generated_at=datetime(2026, 8, 1, tzinfo=UTC),
    )
    current = _observed(
        datetime(2026, 9, 1, tzinfo=UTC),
        (_page("https://example.com/", "a" * 64),),
    )

    comparison = store.compare(store.save(legacy), store.save(current))

    assert comparison.page_history_available is False
    assert comparison.pages_added == ()
    assert comparison.pages_removed == ()
    assert comparison.pages_changed == ()
    assert comparison.page_status_changed == ()
