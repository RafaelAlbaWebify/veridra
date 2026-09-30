from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from fastapi import FastAPI

from veridra.runtime_route_policy import LEGACY_BROWSER_PREFIXES, conceal_legacy_browser_routes


def _isolated_paths(script: str, tmp_path: Path) -> set[str]:
    environment = os.environ.copy()
    environment["VERIDRA_DATA_DIR"] = str(tmp_path / "runtime-data")
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    loaded = json.loads(completed.stdout)
    assert isinstance(loaded, list)
    return {str(item) for item in loaded}


def test_composed_operator_runtime_exposes_only_operator_product_surfaces(
    tmp_path: Path,
) -> None:
    script = """
import json
from veridra.runtime import app
schema = app.openapi()
print(json.dumps(sorted(schema['paths'])))
"""
    environment = os.environ.copy()
    data = tmp_path / "operator"
    environment.update(
        {
            "VERIDRA_ENV": "operator",
            "VERIDRA_IDENTITY_DB": str(data / "identity" / "veridra.sqlite3"),
            "VERIDRA_TENANT_DATA_ROOT": str(data / "tenants"),
            "VERIDRA_TRUSTED_ORIGIN": "http://127.0.0.1:8010",
            "VERIDRA_ALLOWED_HOSTS": "127.0.0.1,localhost",
            "VERIDRA_BIND_HOST": "127.0.0.1",
            "VERIDRA_BIND_PORT": "8010",
        }
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    paths = set(json.loads(completed.stdout))

    for required in (
        "/agency",
        "/agency/prospects",
        "/agency/prospects/discover",
        "/agency/deals",
        "/agency/customers",
        "/agency/projects",
        "/agency/recurring-services",
    ):
        assert required in paths

    for forbidden in (
        "/login",
        "/signup",
        "/onboarding",
        "/plans",
        "/workspace",
        "/members",
        "/agency/leads",
        "/agency/lead-forms",
        "/embed/audit/{form_id}",
        "/api/auth/login",
        "/free",
        "/free/{slug}",
        "/report",
        "/report.pdf",
        "/export",
        "/crawl/assess",
        "/crawl/report",
        "/crawl/report.pdf",
        "/crawl/export",
    ):
        assert forbidden not in paths

    assert any(path.startswith("/api/tenant/") for path in paths)


def test_policy_quarantines_legacy_tree_and_preserves_nonlegacy_routes() -> None:
    app = FastAPI()

    @app.get("/tasks")
    def legacy_page() -> dict[str, bool]:
        return {"legacy": True}

    @app.post("/tasks")
    def legacy_action() -> dict[str, bool]:
        return {"saved": True}

    @app.get("/agency/projects")
    def agency_projects() -> dict[str, bool]:
        return {"agency": True}

    conceal_legacy_browser_routes(app.router.routes)
    schema = app.openapi()["paths"]

    assert "/tasks" not in schema
    assert "get" in schema["/agency/projects"]


def test_standalone_task_router_retains_compatibility_pages(tmp_path: Path) -> None:
    paths = _isolated_paths(
        """
import json
from fastapi import FastAPI
from veridra.task_web import router
app = FastAPI()
app.include_router(router)
schema = app.openapi()
print(json.dumps(sorted(schema['paths'])))
""",
        tmp_path,
    )

    assert "/tasks" in paths
    assert "/projects/{project_id}/tasks" in paths
