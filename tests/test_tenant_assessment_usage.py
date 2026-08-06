from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from starlette.requests import Request

from veridra.core import Assessment, Finding, Status
from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.request_security import bind_verified_request_identity
from veridra.tenant_assessment_usage import assess_for_request, crawled_page_count
from veridra.tenant_workspace_policy import TenantWorkspacePolicy
from veridra.workspace_policy import (
    PlanName,
    UsageEvent,
    UsageKind,
    WorkspaceConfig,
    usage_period,
)

NOW = datetime.now(UTC)


def _identity(tenant_id: str = "a" * 24) -> RequestIdentity:
    return RequestIdentity(
        user_id="b" * 24,
        tenant_id=tenant_id,
        membership_role=TenantRole.owner,
        session_id="c" * 24,
        authenticated_at=NOW,
    )


def _request(tmp_path: Path, identity: RequestIdentity | None) -> Request:
    app = FastAPI()
    app.state.veridra_tenant_data_root = tmp_path / "tenants"
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/assess",
            "headers": [],
            "app": app,
        }
    )
    if identity is not None:
        bind_verified_request_identity(request, identity)
    return request


def _assessment(*, pages: int = 4) -> Assessment:
    return Assessment.build(
        "https://example.com/",
        [
            Finding(
                id="crawl.http-status",
                area="Website health",
                title="Multi-page page response",
                status=Status.passed,
                severity="info",
                summary="Crawl completed.",
                evidence={"crawled_pages": pages},
            )
        ],
        generated_at=NOW,
    )


def test_crawled_page_count_uses_crawl_evidence() -> None:
    assert crawled_page_count(_assessment(pages=7)) == 7


def test_crawled_page_count_falls_back_to_one() -> None:
    assessment = Assessment.build(
        "https://example.com/",
        [],
        generated_at=NOW,
    )
    assert crawled_page_count(assessment) == 1


def test_authenticated_assessment_records_tenant_usage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity = _identity()
    request = _request(tmp_path, identity)
    policy = TenantWorkspacePolicy(tmp_path / "tenants")
    policy.save(identity, WorkspaceConfig(plan=PlanName.agency))
    monkeypatch.setattr(
        "veridra.app.assess_url",
        lambda _url: _assessment(pages=4),
    )

    result = assess_for_request(request, "https://example.com")

    assert result.target.host == "example.com"
    totals = policy.usage_ledger(identity).totals(
        usage_period(policy.load(identity), now=NOW)
    )
    assert totals[UsageKind.audit] == 1
    assert totals[UsageKind.crawled_page] == 4


def test_exhausted_audit_allowance_blocks_before_collection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity = _identity()
    request = _request(tmp_path, identity)
    policy = TenantWorkspacePolicy(tmp_path / "tenants")
    policy.save(identity, WorkspaceConfig(plan=PlanName.free))
    for index in range(3):
        policy.record_usage(
            identity,
            UsageEvent(
                kind=UsageKind.audit,
                quantity=1,
                occurred_at=NOW,
                related_id=f"existing-{index}",
            ),
        )
    called = False

    def fake_assess(_url: str) -> Assessment:
        nonlocal called
        called = True
        return _assessment()

    monkeypatch.setattr("veridra.app.assess_url", fake_assess)

    with pytest.raises(HTTPException) as exc_info:
        assess_for_request(request, "https://example.com")

    assert exc_info.value.status_code == 429
    assert called is False


def test_anonymous_assessment_preserves_unmetered_compatibility(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _request(tmp_path, None)
    monkeypatch.setattr(
        "veridra.app.assess_url",
        lambda _url: _assessment(pages=2),
    )

    assess_for_request(request, "https://example.com")

    assert not (tmp_path / "tenants").exists()
