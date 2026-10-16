"""Contract tests for the isolated real-site review runner (no network)."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

RUNNER = Path(__file__).resolve().parents[1] / "tools" / "live_audit_review_acceptance.py"
SPEC = importlib.util.spec_from_file_location("live_audit_review_acceptance", RUNNER)
assert SPEC is not None and SPEC.loader is not None
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def test_review_summary_keeps_attention_findings_and_review_questions() -> None:
    assessment = SimpleNamespace(model_dump=lambda **_: {
        "mode": "live",
        "target": "https://example.com/",
        "generated_at": "2026-10-16T12:00:00Z",
        "elapsed_ms": 42,
        "summary": {"total": 2, "attention": 1, "passed": 1, "unavailable": 0},
        "area_summary": {},
        "findings": [
            {"id": "one", "area": "SEO", "severity": "medium", "title": "Title",
             "summary": "Missing", "recommendation": "Add one", "status": "attention"},
            {"id": "two", "area": "SEO", "severity": "info", "title": "Canonical",
             "summary": "Present", "recommendation": None, "status": "passed"},
        ],
    })
    summary = runner._review_summary(assessment)
    assert summary["contract"] == "veridra_live_audit_review_v1"
    assert len(summary["attention_findings"]) == 1
    assert summary["attention_findings"][0]["id"] == "one"
    assert len(summary["review_questions"]) == 4
    assert summary["commercial_quality_accepted"] is False
    assert summary["demonstration_site"] is True
    assert "not a representative local business" in summary["applicability_warning"]


def test_public_target_validates_resolved_host(monkeypatch: pytest.MonkeyPatch) -> None:
    visited: list[str] = []
    monkeypatch.setattr(runner, "resolve_public_ips", lambda host: visited.append(host))
    assert runner._public_target("https://example.com/") == "https://example.com/"
    assert visited == ["example.com"]


def test_public_target_rejects_credentials() -> None:
    with pytest.raises(ValueError):
        runner._public_target("https://user:pass@example.com/")
