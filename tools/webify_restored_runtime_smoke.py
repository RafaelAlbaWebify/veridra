"""Read-only functional smoke of a recovered TRON snapshot.

Copies restored inputs into an ephemeral temporary directory and exercises the
private Webify ASGI app in-process. Source snapshot is never used as runtime data.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROUTES = ("/", "/health/live", "/agency", "/signup", "/login", "/plans", "/billing", "/workspace")


def check_restored_runtime(identity_database: Path, tenant_root: Path) -> dict[str, object]:
    if not identity_database.is_file() or not tenant_root.is_dir():
        return {"result": "blocked", "reason": "Restored identity or tenant directory missing."}
    if any(Path(str(identity_database) + ext).exists() for ext in ("-wal", "-shm", "-journal")):
        return {"result": "blocked", "reason": "Identity snapshot has live SQLite sidecars."}
    with tempfile.TemporaryDirectory(prefix="webify-restored-smoke-") as name:
        root = Path(name)
        identity = root / "identity" / "veridra.sqlite3"
        identity.parent.mkdir()
        shutil.copy2(identity_database, identity)
        tenants = root / "tenants"
        shutil.copytree(tenant_root, tenants)
        env = os.environ.copy()
        for key in tuple(env):
            if key.startswith("VERIDRA_"):
                env.pop(key, None)
        env.update({
            "VERIDRA_ENV": "production",
            "VERIDRA_LOCAL_AGENCY": "1",
            "VERIDRA_IDENTITY_DB": str(identity),
            "VERIDRA_TENANT_DATA_ROOT": str(tenants),
            "VERIDRA_BIND_HOST": "127.0.0.1",
            "VERIDRA_BIND_PORT": "8011",
            "VERIDRA_TRUSTED_ORIGIN": "http://127.0.0.1:8011",
            "VERIDRA_ALLOWED_HOSTS": "127.0.0.1,localhost",
        })
        code = """
import json
from fastapi.testclient import TestClient
from veridra.runtime import app

client = TestClient(app, base_url="http://127.0.0.1:8011", client=("127.0.0.1", 50000))
routes = {}
for route in (\n    "/", "/health/live", "/agency", "/signup", "/login", "/plans", "/billing", "/workspace"\n):
    response = client.get(route, follow_redirects=False)
    routes[route] = response.status_code
print("WEBIFY_SMOKE_JSON:" + json.dumps(routes, sort_keys=True))
"""
        try:
            run = subprocess.run(
                [sys.executable, "-c", code],
                cwd=root, env=env, text=True, capture_output=True,
                check=False, timeout=90,
            )
        except subprocess.TimeoutExpired:
            return {"result": "failed", "reason": "ASGI smoke timed out."}
        marker = "WEBIFY_SMOKE_JSON:"
        records = [
            line.split(marker, 1)[1] for line in run.stdout.splitlines()
            if marker in line
        ]
        if run.returncode != 0 or not records:
            return {
                "result": "failed",
                "reason": "Private ASGI startup or route inspection failed.",
                "exit_code": run.returncode,
            }
        routes = json.loads(records[-1])
        healthy = routes.get("/health/live") == 200
        agency_ok = routes.get("/agency") == 200
        saas_hidden = all(
            routes.get(path) == 404
            for path in ("/signup", "/login", "/plans", "/billing", "/workspace")
        )
        return {
            "result": "passed" if healthy and agency_ok and saas_hidden else "failed",
            "routes": routes,
            "identity": "existing_restored_copy",
            "source_data_modified": False,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--identity-db", type=Path, required=True)
    parser.add_argument("--tenant-root", type=Path, required=True)
    args = parser.parse_args()
    result = check_restored_runtime(args.identity_db, args.tenant_root)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["result"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
