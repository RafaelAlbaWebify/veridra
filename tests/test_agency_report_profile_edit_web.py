from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient

from veridra.agency_report_profile_edit_web import router as edit_router
from veridra.agency_report_web import router as report_router
from veridra.identity_tenancy import RequestIdentity, TenantRole
from veridra.project_store import ClientProject
from veridra.report_profiles import ReportProfile
from veridra.request_security import bind_verified_request_identity
from veridra.tenant_profile_store import TenantProfileStore
from veridra.tenant_project_store import TenantProjectStore

NOW = datetime(2026, 8, 20, 8, 30, tzinfo=UTC)
OWNER = RequestIdentity(
    user_id="1" * 24,
    tenant_id="a" * 24,
    membership_role=TenantRole.owner,
    session_id="agency-profile-edit-owner",
    authenticated_at=NOW,
)
VIEWER = RequestIdentity(
    user_id="2" * 24,
    tenant_id="a" * 24,
    membership_role=TenantRole.viewer,
    session_id="agency-profile-edit-viewer",
    authenticated_at=NOW,
)
LOGO = "data:image/png;base64,iVBORw0KGgo="
REPLACEMENT_LOGO = "data:image/jpeg;base64,/9j/2Q=="


def _client(
    tmp_path: Path,
    *,
    with_profile: bool = True,
) -> tuple[TestClient, str, Path, str | None]:
    root = tmp_path / "tenants"
    profiles = TenantProfileStore(root)
    profile_id = None
    if with_profile:
        profile_id = profiles.save(
            OWNER,
            ReportProfile(
                organisation_name="Agency <One>",
                client_name="Client & Co",
                consultant_name="Consultant Name",
                agency_email="agency@example.com",
                agency_phone="+34 600 000 000",
                agency_website="https://agency.example/",
                accent_colour="#123456",
                cover_title="Custom <Review>",
                introduction="Intro & context",
                executive_summary="Existing summary",
                conclusion="Existing conclusion",
                call_to_action_label="Book review",
                call_to_action_url="https://agency.example/book",
                language="es",
                show_raw_evidence=False,
                selected_areas=("Website health", "Trust signals"),
                section_order=("executive_summary", "findings"),
                logo_data_uri=LOGO,
            ),
        )
    projects = TenantProjectStore(root)
    project_id = projects.save(
        OWNER,
        ClientProject.build(
            name="Client Project",
            target_url="https://example.com/",
            client_label="Client Co",
            profile_id=profile_id,
        ),
    )
    app = FastAPI()
    app.state.veridra_tenant_data_root = root

    @app.middleware("http")
    async def identity(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        role = request.headers.get("x-test-role")
        if role == "owner":
            bind_verified_request_identity(request, OWNER)
        elif role == "viewer":
            bind_verified_request_identity(request, VIEWER)
        return await call_next(request)

    app.include_router(edit_router)
    app.include_router(report_router)
    return TestClient(app), project_id, root, profile_id


def test_edit_page_prefills_and_escapes_saved_profile(tmp_path: Path) -> None:
    client, project_id, _, profile_id = _client(tmp_path)

    response = client.get(
        f"/agency/projects/{project_id}/reports/profile/edit",
        headers={"x-test-role": "owner"},
    )

    assert response.status_code == 200
    assert profile_id is not None
    assert f"Editing saved profile:</strong> {profile_id}" in response.text
    assert "value='Agency &lt;One&gt;'" in response.text
    assert "value='Client &amp; Co'" in response.text
    assert "value='Custom &lt;Review&gt;'" in response.text
    assert "Intro &amp; context" in response.text
    assert "Existing summary" in response.text
    assert "value='es' selected" in response.text
    assert "value='#123456'" in response.text
    assert "value='Website health'" not in response.text
    assert "Website health\nTrust signals" in response.text
    assert "value='executive_summary' checked" in response.text
    assert "value='findings' checked" in response.text
    assert "An embedded logo is currently saved." in response.text
    assert "name='remove_logo'" in response.text


def test_edit_page_requires_saved_profile_and_manage_permission(tmp_path: Path) -> None:
    client, project_id, _, _ = _client(tmp_path, with_profile=False)

    owner = client.get(
        f"/agency/projects/{project_id}/reports/profile/edit",
        headers={"x-test-role": "owner"},
    )
    viewer = client.get(
        f"/agency/projects/{project_id}/reports/profile/edit",
        headers={"x-test-role": "viewer"},
    )

    assert owner.status_code == 404
    assert viewer.status_code == 403


def test_save_replaces_profile_in_place_and_preserves_project_identity(tmp_path: Path) -> None:
    client, project_id, root, profile_id = _client(tmp_path)
    assert profile_id is not None

    response = client.post(
        f"/agency/projects/{project_id}/reports/profile/edit",
        headers={"x-test-role": "owner"},
        data={
            "organisation_name": "Agency Updated",
            "client_name": "Client Updated",
            "consultant_name": "New Consultant",
            "agency_email": "updated@example.com",
            "agency_phone": "+34 611 111 111",
            "agency_website": "https://updated.example/",
            "accent_colour": "#654321",
            "cover_title": "Updated Website Review",
            "introduction": "Updated intro",
            "executive_summary": "Updated summary",
            "conclusion": "Updated conclusion",
            "call_to_action_label": "Schedule call",
            "call_to_action_url": "https://updated.example/call",
            "language": "en",
            "show_raw_evidence": "yes",
            "selected_areas": "Search visibility, Security posture\nSearch visibility",
            "sections": ["executive_summary", "priority_actions", "findings"],
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == (
        f"/agency/projects/{project_id}/reports?profile=updated"
    )
    projects = TenantProjectStore(root)
    project = projects.load(OWNER, projects.ref(OWNER, project_id))
    assert project.profile_id == profile_id
    assert len(projects.list(OWNER)) == 1
    profiles = TenantProfileStore(root)
    assert len(profiles.list(OWNER)) == 1
    saved = profiles.load(OWNER, profiles.ref(OWNER, profile_id))
    assert saved.organisation_name == "Agency Updated"
    assert saved.client_name == "Client Updated"
    assert saved.accent_colour == "#654321"
    assert saved.language == "en"
    assert saved.show_raw_evidence is True
    assert saved.selected_areas == ("Search visibility", "Security posture")
    assert saved.section_order == ("executive_summary", "priority_actions", "findings")
    assert saved.logo_data_uri == LOGO


def test_save_can_replace_or_remove_logo(tmp_path: Path) -> None:
    client, project_id, root, profile_id = _client(tmp_path)
    assert profile_id is not None
    base = {
        "organisation_name": "Agency One",
        "language": "en",
        "accent_colour": "#123456",
        "sections": ["executive_summary", "findings"],
    }

    replaced = client.post(
        f"/agency/projects/{project_id}/reports/profile/edit",
        headers={"x-test-role": "owner"},
        data={**base, "logo_data_uri": REPLACEMENT_LOGO},
        follow_redirects=False,
    )
    profile = TenantProfileStore(root).load(
        OWNER,
        TenantProfileStore.ref(OWNER, profile_id),
    )
    assert replaced.status_code == 303
    assert profile.logo_data_uri == REPLACEMENT_LOGO

    removed = client.post(
        f"/agency/projects/{project_id}/reports/profile/edit",
        headers={"x-test-role": "owner"},
        data={**base, "remove_logo": "yes"},
        follow_redirects=False,
    )
    profile = TenantProfileStore(root).load(
        OWNER,
        TenantProfileStore.ref(OWNER, profile_id),
    )
    assert removed.status_code == 303
    assert profile.logo_data_uri is None


def test_save_rejects_invalid_input_without_replacing_profile(tmp_path: Path) -> None:
    client, project_id, root, profile_id = _client(tmp_path)
    assert profile_id is not None
    profiles = TenantProfileStore(root)
    before = profiles.load(OWNER, profiles.ref(OWNER, profile_id))

    response = client.post(
        f"/agency/projects/{project_id}/reports/profile/edit",
        headers={"x-test-role": "owner"},
        data={
            "organisation_name": "Agency One",
            "language": "en",
            "accent_colour": "not-a-colour",
        },
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert profiles.load(OWNER, profiles.ref(OWNER, profile_id)) == before


def test_report_hub_exposes_edit_only_for_saved_profile(tmp_path: Path) -> None:
    client, project_id, _, _ = _client(tmp_path)
    saved = client.get(
        f"/agency/projects/{project_id}/reports",
        headers={"x-test-role": "owner"},
    )
    other_client, other_project_id, _, _ = _client(
        tmp_path / "default",
        with_profile=False,
    )
    default = other_client.get(
        f"/agency/projects/{other_project_id}/reports",
        headers={"x-test-role": "owner"},
    )

    assert saved.status_code == 200
    assert "Edit current saved profile" in saved.text
    assert f"/agency/projects/{project_id}/reports/profile/edit" in saved.text
    assert default.status_code == 200
    assert "Edit current saved profile" not in default.text
