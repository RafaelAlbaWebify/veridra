from __future__ import annotations

from fastapi import FastAPI
from fastapi.routing import APIRoute

from veridra.runtime import app as composed_app
from veridra.runtime_route_policy import LEGACY_BROWSER_PREFIXES, conceal_legacy_browser_routes
from veridra.task_web import router as standalone_task_router


def _browser_get_paths(app: FastAPI) -> set[str]:
    return {
        route.path
        for route in app.router.routes
        if isinstance(route, APIRoute)
        and bool((route.methods or set()).intersection({"GET", "HEAD"}))
    }


def test_composed_runtime_has_one_authoritative_operator_journey() -> None:
    paths = _browser_get_paths(composed_app)

    assert "/agency" in paths
    assert "/agency/projects" in paths
    assert "/agency/leads" in paths
    assert "/workspace" in paths
    assert "/workspace/members" in paths
    assert "/onboarding" in paths
    assert "/embed/audit/{form_id}" in paths
    assert any(path.startswith("/api/tenant/") for path in paths)

    for path in paths:
        assert not any(
            path == prefix or path.startswith(f"{prefix}/")
            for prefix in LEGACY_BROWSER_PREFIXES
        )


def test_policy_preserves_post_handlers_and_nonlegacy_routes() -> None:
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

    routes = [route for route in app.router.routes if isinstance(route, APIRoute)]
    assert not any(route.path == "/tasks" and route.methods == {"GET"} for route in routes)
    assert any(route.path == "/tasks" and route.methods == {"POST"} for route in routes)
    assert any(route.path == "/agency/projects" for route in routes)


def test_standalone_task_router_retains_compatibility_pages() -> None:
    app = FastAPI()
    app.include_router(standalone_task_router)

    paths = _browser_get_paths(app)

    assert "/tasks" in paths
    assert "/projects/{project_id}/tasks" in paths
