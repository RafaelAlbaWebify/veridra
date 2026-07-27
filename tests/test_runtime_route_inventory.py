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


def test_composed_runtime_has_one_authoritative_operator_journey(tmp_path: Path) -> None:
    paths = _isolated_paths(
        """
import json
from veridra.runtime import app
schema = app.openapi()
paths = sorted(schema['paths'])
print(json.dumps(paths))
""",
        tmp_path,
    )

    assert "/agency" in paths
    assert "/agency/projects" in paths
    assert "/agency/leads" in paths
    assert "/workspace" in paths
    assert "/members" in paths
    assert "/members/audit" in paths
    assert "/onboarding" in paths
    assert "/embed/audit/{form_id}" in paths
    assert any(path.startswith("/api/tenant/") for path in paths)

    offenders = {
        path
        for path in paths
        if any(
            path == prefix or path.startswith(f"{prefix}/")
            for prefix in LEGACY_BROWSER_PREFIXES
        )
    }
    assert not offenders, sorted(offenders)


def test_policy_removes_legacy_route_tree_and_preserves_nonlegacy_routes() -> None:
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
