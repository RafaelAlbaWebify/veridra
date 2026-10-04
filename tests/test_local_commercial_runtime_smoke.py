from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_full_local_commercial_runtime_imports_without_public_only_dependencies(
    tmp_path: Path,
) -> None:
    identity = tmp_path / "identity" / "veridra.sqlite3"
    tenants = tmp_path / "tenants"
    env = os.environ.copy()
    for name in (
        "VERIDRA_PRIVACY_URL",
        "VERIDRA_TERMS_URL",
        "VERIDRA_SMTP_HOST",
        "VERIDRA_SMTP_SENDER",
        "VERIDRA_SMTP_USERNAME",
        "VERIDRA_SMTP_PASSWORD",
        "VERIDRA_STRIPE_SECRET_KEY",
        "VERIDRA_STRIPE_WEBHOOK_SECRET",
        "VERIDRA_STRIPE_PRICE_SOLO",
        "VERIDRA_STRIPE_PRICE_PROFESSIONAL",
        "VERIDRA_STRIPE_PRICE_AGENCY",
    ):
        env.pop(name, None)
    env.update(
        {
            "VERIDRA_ENV": "production",
            "VERIDRA_IDENTITY_DB": str(identity),
            "VERIDRA_TENANT_DATA_ROOT": str(tenants),
            "VERIDRA_TRUSTED_ORIGIN": "http://127.0.0.1:8011",
            "VERIDRA_ALLOWED_HOSTS": "127.0.0.1,localhost",
            "VERIDRA_BIND_HOST": "127.0.0.1",
            "VERIDRA_BIND_PORT": "8011",
            "VERIDRA_LOCAL_AGENCY": "1",
        }
    )
    code = """
import os
from pathlib import Path

from fastapi.testclient import TestClient

from veridra.identity_bootstrap import BOOTSTRAP_CONFIRMATION, SQLiteIdentityBootstrap

database = Path(os.environ["VERIDRA_IDENTITY_DB"])
SQLiteIdentityBootstrap(database).create_first_owner(
    tenant_slug="webify-local",
    tenant_name="Webify",
    owner_email="owner@example.com",
    owner_name="Local owner",
    password="local-test-password-123",
    confirmation=BOOTSTRAP_CONFIRMATION,
)

from veridra.runtime import app
from veridra.runtime_config import RuntimeEnvironment

runtime = app.state.veridra_runtime_config
assert runtime.environment is RuntimeEnvironment.production
assert runtime.is_loopback_local is True
assert runtime.local_agency is True
client = TestClient(
    app,
    base_url="http://127.0.0.1:8011",
    client=("127.0.0.1", 50000),
)

root = client.get("/", follow_redirects=False)
assert root.status_code == 302
assert root.headers["location"] == "/agency"

agency = client.get("/agency")
assert agency.status_code == 200
assert "WEBIFY · VERIDRA LOCAL" in agency.text
assert "There is no VERIDRA subscription" in agency.text
assert "href='/agency/prospects/discover'" in agency.text
assert "href='/agency/leads'" in agency.text
assert "href='/agency/lead-forms'" in agency.text

for path in ("/signup", "/login", "/plans", "/billing", "/workspace", "/workspace/members"):
    assert client.get(path).status_code == 404

assert not hasattr(app.state, "veridra_legal_links")
assert not hasattr(app.state, "veridra_smtp_config")
assert not hasattr(app.state, "veridra_stripe_billing")
"""

    completed = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert completed.returncode == 0, completed.stderr
    assert identity.exists()
