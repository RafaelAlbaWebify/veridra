from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from starlette.requests import Request

from veridra.identity_tenancy import IdentityBoundaryError, RequestIdentity, TenantRole
from veridra.report_profiles import ReportProfile
from veridra.tenant_profile_api import create_profile, get_profile, list_profiles
from veridra.tenant_profile_store import TenantProfileStore

NOW = datetime(2026, 7, 25, 21, 0, tzinfo=UTC)


def _identity(tenant_id: str, role: TenantRole) -> RequestIdentity:
    return RequestIdentity(
        user_id="a" * 24,
        tenant_id=tenant_id,
        membership_role=role,
        session_id="b" * 24,
        authenticated_at=NOW,
    )


def _request(root: Path) -> Request:
    app = FastAPI()
    app.state.veridra_tenant_data_root = root
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/tenant/report-profiles",
            "headers": [],
            "app": app,
        }
    )


def _profile() -> ReportProfile:
    return ReportProfile(
        organisation_name="Northwind Security",
        client_name="Contoso",
        consultant_name="Rafael Alba",
        language="en",
    )


def test_same_profile_id_is_isolated_between_tenants(tmp_path: Path) -> None:
    store = TenantProfileStore(tmp_path / "tenants")
    first = _identity("1" * 24, TenantRole.sales)
    second = _identity("2" * 24, TenantRole.sales)
    profile = _profile()

    first_id = store.save(first, profile)
    second_id = store.save(second, profile)

    assert first_id == second_id
    assert store.load(first, store.ref(first, first_id)) == profile
    assert store.load(second, store.ref(second, second_id)) == profile
    assert (
        tmp_path
        / "tenants"
        / first.tenant_id
        / "report-profiles"
        / f"{first_id}.json"
    ).exists()
    assert (
        tmp_path
        / "tenants"
        / second.tenant_id
        / "report-profiles"
        / f"{second_id}.json"
    ).exists()


def test_viewer_reads_and_analyst_manages_profiles(tmp_path: Path) -> None:
    root = tmp_path / "tenants"
    analyst = _identity("3" * 24, TenantRole.analyst)
    viewer = _identity("3" * 24, TenantRole.viewer)
    request = _request(root)

    profile_id = create_profile(_profile(), request, analyst)["id"]

    assert get_profile(profile_id, request, viewer) == _profile()
    assert list_profiles(request, viewer)[0].id == profile_id


def test_viewer_cannot_manage_profiles(tmp_path: Path) -> None:
    store = TenantProfileStore(tmp_path / "tenants")
    viewer = _identity("4" * 24, TenantRole.viewer)

    with pytest.raises(IdentityBoundaryError):
        store.save(viewer, _profile())


def test_cross_tenant_profile_is_not_visible(tmp_path: Path) -> None:
    root = tmp_path / "tenants"
    first = _identity("5" * 24, TenantRole.sales)
    second = _identity("6" * 24, TenantRole.viewer)
    request = _request(root)
    profile_id = create_profile(_profile(), request, first)["id"]

    with pytest.raises(Exception) as captured:
        get_profile(profile_id, request, second)

    assert getattr(captured.value, "status_code", None) == 404
