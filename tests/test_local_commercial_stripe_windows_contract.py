from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_commercial_launcher_stores_stripe_test_secrets_outside_repository() -> None:
    script = (ROOT / "scripts" / "windows" / "veridra-commercial-local.ps1").read_text(
        encoding="utf-8"
    )

    assert "Join-Path $env:LOCALAPPDATA 'VeridraCommercial'" in script
    assert "$StripeConfigFile = Join-Path $ConfigRoot 'stripe.json'" in script
    assert "$StripeSecretKeyFile = Join-Path $ConfigRoot 'stripe-secret-key.txt'" in script
    assert "$StripeWebhookSecretFile = Join-Path $ConfigRoot 'stripe-webhook-secret.txt'" in script
    assert "ConvertFrom-SecureString" in script
    assert "Read-ProtectedSecret" in script
    assert "VERIDRA_STRIPE_SECRET_KEY" in script
    assert "VERIDRA_STRIPE_WEBHOOK_SECRET" in script
    assert "Only a Stripe test-mode secret key" in script
    assert "Write-Host $env:VERIDRA_STRIPE_SECRET_KEY" not in script
    assert "Write-Host $env:VERIDRA_STRIPE_WEBHOOK_SECRET" not in script


def test_commercial_stripe_listener_is_loopback_only_and_verifies_signing_secret() -> None:
    script = (ROOT / "scripts" / "windows" / "veridra-commercial-local.ps1").read_text(
        encoding="utf-8"
    )

    assert "listen --print-secret" in script
    assert "http://127.0.0.1:$Port/api/billing/stripe/webhook" in script
    assert "--forward-to $endpoint" in script
    assert "customer.subscription.created" in script
    assert "customer.subscription.updated" in script
    assert "customer.subscription.deleted" in script
    assert "invoice.payment_failed" not in script
    assert "invoice.payment_succeeded" not in script
    assert "0.0.0.0" not in script


def test_commercial_stripe_batch_launchers_use_dedicated_local_launcher() -> None:
    commands = {
        "VERIDRA_COMMERCIAL_STRIPE_CONFIG.bat": "stripe-config",
        "VERIDRA_COMMERCIAL_STRIPE_LISTEN.bat": "stripe-listen",
        "VERIDRA_COMMERCIAL_STRIPE_CLEAR.bat": "stripe-clear",
        "VERIDRA_COMMERCIAL_PROVIDER_PREFLIGHT.bat": "provider-preflight",
        "VERIDRA_COMMERCIAL_PROVIDER_SNAPSHOT.bat": "provider-snapshot",
        "VERIDRA_COMMERCIAL_PROVIDER_RECONCILE.bat": "provider-reconcile",
    }
    for filename, command in commands.items():
        body = (ROOT / filename).read_text(encoding="utf-8")
        assert "veridra-commercial-local.ps1" in body
        assert f" {command} %*" in body


def test_commercial_provider_snapshot_launcher_writes_secret_free_evidence() -> None:
    script = (ROOT / "scripts" / "windows" / "veridra-commercial-local.ps1").read_text(
        encoding="utf-8"
    )

    assert "provider-snapshot" in script
    assert "veridra.local_provider_snapshot" in script
    assert "VERIDRA_COMMERCIAL_PROVIDER_STATE_" in script
    assert "--tenant-id $checkedTenant" in script


def test_commercial_provider_reconciliation_is_read_only_by_default() -> None:
    script = (ROOT / "scripts" / "windows" / "veridra-commercial-local.ps1").read_text(
        encoding="utf-8"
    )

    assert "provider-reconcile" in script
    assert "veridra.local_provider_reconcile" in script
    assert "Checking Stripe vs VERIDRA state read-only." in script
    assert "if ($Apply.IsPresent)" in script
    assert "$reconcileArgs += '--apply'" in script
    assert "VERIDRA_COMMERCIAL_PROVIDER_RECONCILIATION_" in script
    assert "'provider-reconcile' { Invoke-ProviderReconcile }" in script
