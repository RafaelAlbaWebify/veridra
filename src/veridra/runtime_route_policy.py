from __future__ import annotations

from typing import cast

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


def is_legacy_browser_route(route: BaseRoute) -> bool:
    """Return whether a route belongs to a standalone compatibility tree."""

    path = getattr(route, "path", None)
    if not isinstance(path, str):
        return False
    if path.startswith("/agency") or path.startswith("/api"):
        return False
    return any(
        path == prefix or path.startswith(f"{prefix}/")
        for prefix in LEGACY_BROWSER_PREFIXES
    )


def conceal_legacy_browser_routes(routes: list[BaseRoute]) -> None:
    """Remove standalone compatibility route trees from the composed runtime."""

    for route in routes:
        nested = getattr(route, "routes", None)
        if isinstance(nested, list):
            conceal_legacy_browser_routes(cast(list[BaseRoute], nested))
    routes[:] = [route for route in routes if not is_legacy_browser_route(route)]
