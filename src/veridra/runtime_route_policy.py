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


def _method_name(method: object) -> str:
    value = getattr(method, "value", method)
    return str(value).upper()


def _route_contract(route: BaseRoute) -> tuple[str, set[str]] | None:
    path = getattr(route, "path", None)
    methods = getattr(route, "methods", None)
    if not isinstance(path, str) or methods is None:
        return None
    return path, {_method_name(method) for method in methods}


def is_legacy_browser_route(route: BaseRoute) -> bool:
    """Return whether a route is a duplicate standalone browser surface."""

    contract = _route_contract(route)
    if contract is None:
        return False
    path, methods = contract
    if not methods.intersection({"GET", "HEAD"}):
        return False
    if path.startswith("/agency") or path.startswith("/api"):
        return False
    return any(
        path == prefix or path.startswith(f"{prefix}/")
        for prefix in LEGACY_BROWSER_PREFIXES
    )


def conceal_legacy_browser_routes(routes: list[BaseRoute]) -> None:
    """Remove duplicate standalone browser pages from a composed route tree in place."""

    for route in routes:
        nested = getattr(route, "routes", None)
        if isinstance(nested, list):
            conceal_legacy_browser_routes(cast(list[BaseRoute], nested))
    routes[:] = [route for route in routes if not is_legacy_browser_route(route)]
