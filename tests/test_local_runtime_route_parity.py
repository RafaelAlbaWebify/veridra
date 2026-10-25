"""Assert that canonical local mode preserves Webify's commercial route surface."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import TypedDict, cast



class RouteInventory(TypedDict):
    routes: list[tuple[str, str]]
    environment: str
    local_agency: bool
    loopback: bool


def _inventory(tmp_path: Path) -> RouteInventory:
    env = {k: v for k, v in os.environ.items() if not k.startswith("VERIDRA_")}
    env.update({
        "VERIDRA_ENV": "local",
        "VERIDRA_IDENTITY_DB": str(tmp_path / "identity" / "veridra.sqlite3"),
        "VERIDRA_TENANT_DATA_ROOT": str(tmp_path / "tenants"),
        "VERIDRA_TRUSTED_ORIGIN": "http://127.0.0.1:8011",
        "VERIDRA_ALLOWED_HOSTS": "127.0.0.1,localhost",
        "VERIDRA_BIND_HOST": "127.0.0.1",
        "VERIDRA_BIND_PORT": "8011",
    })
    code = """
import json
from veridra.runtime import app
config = app.state.veridra_runtime_config
routes = sorted(
    (method.upper(), path)
    for path, operations in app.openapi()["paths"].items()
    for method in operations
    if method.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE"}
)
print(json.dumps({
    "routes": routes,
    "environment": config.environment.value,
    "local_agency": config.local_agency,
    "loopback": config.is_loopback_local,
}))
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        capture_output=True,
        text=True,
        check=True,
        timeout=45,
    )
    data = json.loads(result.stdout)
    if not isinstance(data, dict):
        raise ValueError("Runtime inventory must be an object.")
    routes = data.get("routes")
    if not isinstance(routes, list) or any(
        not isinstance(item, list)
        or len(item) != 2
        or not all(isinstance(value, str) for value in item)
        for item in routes
    ):
        raise ValueError("Runtime inventory routes must be method/path pairs.")
    data["routes"] = [tuple(item) for item in routes]
    return cast(RouteInventory, data)


def test_canonical_local_exposes_commercial_routes(tmp_path: Path) -> None:
    inventory = _inventory(tmp_path)
    assert inventory["environment"] == "local"
    assert inventory["local_agency"] is True
    assert inventory["loopback"] is True
    for route in (
        ("GET", "/agency/prospects"),
        ("GET", "/agency/leads"),
        ("GET", "/agency/lead-forms"),
    ):
        assert route in inventory["routes"]


def test_canonical_local_excludes_hosted_saas_routes(tmp_path: Path) -> None:
    inventory = _inventory(tmp_path)
    routes = {path for _, path in inventory["routes"]}
    for path in ("/signup", "/login", "/plans", "/billing", "/workspace"):
        assert path not in routes
