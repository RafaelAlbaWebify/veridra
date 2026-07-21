from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import veridra.project_web as project_web
from veridra.app import app
from veridra.core import Assessment, Finding, Status

client = TestClient(app)


def _assessment(moment: datetime, *, changed: bool = False) -> Assessment:
    findings = [
        Finding(
            id="health.title",
            area="Website health",
            title="Document title",
            status=Status.passed if not changed else Status.attention,
            severity="info" if not changed else "medium",
            summary="Title is present." if not changed else "Title is absent.",
            recommendation=None if not changed else "Add a title.",
        )
    ]
    if changed:
        findings.append(
            Finding(
                id="local.visible-phone",
                area="Local presence",
                title="Visible telephone route",
                status=Status.passed,
                severity="info",
                summary="Telephone is present.",
            )
        )
    return Assessment.build(
        "https://example.com/",
        findings,
        generated_at=moment,
    )


def _create_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("VERIDRA_DATA_DIR", str(tmp_path))
    response = client.post(
        "/projects",
        data={"name": "Example client", "target_url": "example.com"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    return str(response.headers["location"]).rsplit("/", 1)[1]


def test_project_monitoring_first_and_second_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry_id = _create_project(tmp_path, monkeypatch)
    first = _assessment(datetime(2026, 7, 21, 10, 0, tzinfo=UTC))
    second = _assessment(
        datetime(2026, 7, 21, 11, 0, tzinfo=UTC),
        changed=True,
    )
    assessments = iter((first, second))
    monkeypatch.setattr(project_web, "assess_url", lambda url: next(assessments))

    initial = client.get(f"/projects/{entry_id}/monitor")
    assert initial.status_code == 200
    assert "No project assessments have been saved yet." in initial.text

    first_run = client.post(
        f"/projects/{entry_id}/monitor/run",
        follow_redirects=False,
    )
    assert first_run.status_code == 303
    after_first = client.get(first_run.headers["location"])
    assert "Saved runs" in after_first.text
    assert "Run and save at least two distinct assessments" in after_first.text

    second_run = client.post(
        f"/projects/{entry_id}/monitor/run",
        follow_redirects=False,
    )
    assert second_run.status_code == 303
    after_second = client.get(second_run.headers["location"])
    assert "Latest assessment compared" in after_second.text
    assert "Open full comparison" in after_second.text
    assert "Added" in after_second.text
    assert "Changed" in after_second.text
    assert first.generated_at.isoformat() in after_second.text
    assert second.generated_at.isoformat() in after_second.text


def test_duplicate_project_run_is_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry_id = _create_project(tmp_path, monkeypatch)
    assessment = _assessment(datetime(2026, 7, 21, 10, 0, tzinfo=UTC))
    monkeypatch.setattr(project_web, "assess_url", lambda url: assessment)

    client.post(f"/projects/{entry_id}/monitor/run")
    client.post(f"/projects/{entry_id}/monitor/run")

    page = client.get(f"/projects/{entry_id}/monitor")
    assert page.text.count("<code>") == 1
    assert "Run and save at least two distinct assessments" in page.text


def test_project_monitoring_ignores_other_targets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry_id = _create_project(tmp_path, monkeypatch)
    other = Assessment.build(
        "https://other.example/",
        [],
        generated_at=datetime(2026, 7, 21, 9, 0, tzinfo=UTC),
    )
    from veridra.history import HistoryStore

    HistoryStore().save(other)
    page = client.get(f"/projects/{entry_id}/monitor")
    assert "other.example" not in page.text
    assert "No project assessments have been saved yet." in page.text


def test_missing_project_monitor_returns_404(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VERIDRA_DATA_DIR", str(tmp_path))
    response = client.get(f"/projects/{'a' * 24}/monitor")
    assert response.status_code == 404


def test_project_monitoring_escapes_project_content(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VERIDRA_DATA_DIR", str(tmp_path))
    response = client.post(
        "/projects",
        data={
            "name": "<script>bad()</script>",
            "client_label": "A & B",
            "target_url": "example.com",
        },
        follow_redirects=False,
    )
    entry_id = str(response.headers["location"]).rsplit("/", 1)[1]
    page = client.get(f"/projects/{entry_id}/monitor")
    assert "<script>bad()</script>" not in page.text
    assert "&lt;script&gt;bad()&lt;/script&gt;" in page.text
    assert "A &amp; B" in page.text
