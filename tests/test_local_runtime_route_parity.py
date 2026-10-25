"""Assert that canonical local mode preserves Webify's commercial route surface."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


def _inventory(tmp_path: Path, *, legacy: bool) -> dict[str, object]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("VERIDRA_")}
    env.update({
        "VERIDRA_ENV": "production" if legacy else "local",
        "VERIDRA_IDENTITY_DB": str(tmp_path / "identity" / "veridra.sqlite3"),
        "VERIDRA_TENANT_DATA_ROOT": str(tmp_path / "tenants"),
        "VERIDRA_TRUSTED_ORIGIN": "http://127.0.0.1:8011",
        "VERIDRA_ALLOWED_HOSTS": "127.0.0.1,localhost",
        "VERIDRA_BIND_HOST": "127.0.0.1",
        "VERIDRA_BIND_PORT": "8011",
    })
    if legacy:
        env["VERIDRA_LOCAL_AGENCY"] = "1"
    code = """
import json
from veridra.runtime import app
config = app.state.veridra_runtime_config
routes = sorted(
    (method, route.path)
    for route in app.routes
    for method in (getattr(route, "methods", None) or ())
    if method not in {"HEAD", "OPTIONS"}
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
    return json.loads(result.stdout)


def test_canonical_local_has_exact_commercial_route_parity(tmp_path: Path) -> None:
    old = _inventory(tmp_path / "legacy", legacy=True)
    new = _inventory(tmp_path / "canonical", legacy=False)
    assert old["environment"] == "production"
    assert new["environment"] == "local"
    assert old["local_agency"] is True
    assert new["local_agency"] is True
    assert old["loopback"] is True
    assert new["loopback"] is True
    assert new["routes"] == old["routes"]
    assert ("GET", "/agency/prospects") in new["routes"]
    assert ("GET", "/agency/leads") in new["routes"]
    assert ("GET", "/agency/lead-forms") in new["routes"]


@pytest.mark.parametrize("legacy", [False, True])
def test_private_profiles_exclude_hosted_saas_routes(
    tmp_path: Path, legacy: bool
) -> None:
    inventory = _inventory(tmp_path, legacy=legacy)
    routes = {path for _, path in inventory["routes"]}
    for path in ("/signup", "/login", "/plans", "/billing", "/workspace"):
        assert path not in routes
