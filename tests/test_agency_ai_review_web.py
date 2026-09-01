# ruff: noqa: E501
from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient

from veridra.agency_ai_review_web import router
from veridra.ai_review_exchange import result_integrity_hash
from veridra.core import Assessment, Finding, Status
from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.project_store import ClientProject
from veridra.request_security import bind_verified_request_identity
from veridra.tenant_history_store import TenantHistoryStore
from veridra.tenant_project_store import TenantProjectStore

NOW = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
OWNER = RequestIdentity(
    user_id="1" * 24,
    tenant_id="a" * 24,
    membership_role=TenantRole.owner,
    session_id="ai-review-owner-session-0001",
    authenticated_at=NOW,
)
OTHER = RequestIdentity(
    user_id="2" * 24,
    tenant_id="b" * 24,
    membership_role=TenantRole.owner,
    session_id="ai-review-other-session-0001",
    authenticated_at=NOW,
)


def _app(root: Path) -> TestClient:
    app = FastAPI()
    app.state.veridra_tenant_data_root = root

    @app.middleware("http")
    async def identity(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        bind_verified_request_identity(
            request,
            OTHER if request.headers.get("x-test-tenant") == "other" else OWNER,
        )
        return await call_next(request)

    app.include_router(router)
    return TestClient(app)


def _project_with_assessment(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "tenants"
    project_id = TenantProjectStore(root).save(
        OWNER,
        ClientProject.build(name="AI Review Client", target_url="https://example.com"),
    )
    assessment = Assessment.build(
        "https://example.com",
        [
            Finding(
                id="privacy-link",
                area="Trust",
                title="Privacy link needs attention",
                status=Status.attention,
                severity="medium",
                summary="The saved assessment found a trust-path issue.",
                recommendation="Review the privacy-link destination.",
                evidence={"path": "/privacy"},
            )
        ],
        generated_at=NOW,
    )
    TenantHistoryStore(root).save(OWNER, project_id, assessment)
    return root, project_id


def _review_result(bundle: dict[str, object]) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "exchange_type": "veridra_ai_review_result",
        "review_id": "review-browser-fixture-001",
        "source_bundle_id": bundle["bundle_id"],
        "source_bundle_hash_sha256": bundle["bundle_hash_sha256"],
        "generated_at": (NOW + timedelta(minutes=10)).isoformat(),
        "model_provenance": "GPT fixture",
        "tool_provenance": "structured JSON acceptance",
        "interpretation": "The evidence supports a bounded trust-path improvement.",
        "strengths": ["The issue is directly traceable to saved evidence."],
        "weaknesses_gaps": ["The trust path needs operator review."],
        "opportunity_assessment": "A small evidence-backed remediation opportunity exists.",
        "confidence": "high",
        "uncertainty": ["No conversion impact is known."],
        "recommended_next_action": "Review the privacy destination before deciding remediation.",
        "suggested_messaging_positioning": ["Describe the observed trust-path issue without estimating lost business."],
        "evidence_refs": ["finding:privacy-link"],
        "safe_actions": [
            {
                "action": "request_human_review",
                "reason": "Human verification is appropriate before any workflow action.",
                "evidence_refs": ["finding:privacy-link"],
            }
        ],
    }
    payload["result_hash_sha256"] = result_integrity_hash(payload)
    return payload


def test_project_ai_review_export_import_view_round_trip(tmp_path: Path) -> None:
    root, project_id = _project_with_assessment(tmp_path)
    client = _app(root)

    landing = client.get(f"/agency/projects/{project_id}/ai-review")
    assert landing.status_code == 200
    assert "Export AI review JSON" in landing.text
    assert "Import reviewed result" in landing.text

    exported = client.get(f"/agency/projects/{project_id}/ai-review/export")
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("application/json")
    assert "attachment" in exported.headers["content-disposition"]
    bundle = exported.json()
    assert bundle["exchange_type"] == "veridra_ai_review_bundle"
    assert bundle["context"]["assessment_id"]
    assert bundle["evidence"][0]["evidence_id"] == "finding:privacy-link"

    result = _review_result(bundle)
    imported = client.post(
        f"/agency/projects/{project_id}/ai-review/import",
        data={"result_json": json.dumps(result)},
        follow_redirects=False,
    )
    assert imported.status_code == 303
    assert imported.headers["location"].endswith("?imported=true")

    history = client.get(f"/agency/projects/{project_id}/ai-review")
    assert "review-browser-fixture-001" in history.text
    assert "GPT fixture" in history.text

    viewed = client.get(
        f"/agency/projects/{project_id}/ai-review/results/review-browser-fixture-001"
    )
    assert viewed.status_code == 200
    assert "AI interpretation — imported reasoning, not VERIDRA observation" in viewed.text
    assert "No conversion impact is known" in viewed.text
    assert "request_human_review" in viewed.text
    assert "No outreach has been sent" in viewed.text


def test_project_ai_review_rejects_tampered_result(tmp_path: Path) -> None:
    root, project_id = _project_with_assessment(tmp_path)
    client = _app(root)
    bundle = client.get(f"/agency/projects/{project_id}/ai-review/export").json()
    result = _review_result(bundle)
    result["interpretation"] = "Tampered content."

    response = client.post(
        f"/agency/projects/{project_id}/ai-review/import",
        data={"result_json": json.dumps(result)},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "/ai-review/import?error=" in response.headers["location"]
    assert "integrity" in response.headers["location"].lower()


def test_project_ai_review_conceals_cross_tenant_context(tmp_path: Path) -> None:
    root, project_id = _project_with_assessment(tmp_path)

    response = _app(root).get(
        f"/agency/projects/{project_id}/ai-review",
        headers={"x-test-tenant": "other"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Project not found."}
