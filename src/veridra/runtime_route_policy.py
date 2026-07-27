from __future__ import annotations

from fastapi.routing import APIRoute
from starlette.routing import BaseRoute

LEGACY_BROWSER_PREFIXES = (
    "/commercial",
    "/history",
    "/lead-forms",
    "/leads",
    "/monitoring",
    "/profiles",
    "/projects",
    "/tasks",
)


def is_legacy_browser_route(route: APIRoute) -> bool:
    """Return whether a route is a duplicate standalone browser surface."""

    methods = route.methods or set()
    if not methods.intersection({"GET", "HEAD"}):
        return False
    if route.path.startswith("/agency") or route.path.startswith("/api"):
        return False
    return any(
        route.path == prefix or route.path.startswith(f"{prefix}/")
        for prefix in LEGACY_BROWSER_PREFIXES
    )


def conceal_legacy_browser_routes(routes: list[BaseRoute]) -> None:
    """Remove duplicate standalone browser pages from a composed route list in place."""

    routes[:] = [
        route
        for route in routes
        if not (isinstance(route, APIRoute) and is_legacy_browser_route(route))
    ]
