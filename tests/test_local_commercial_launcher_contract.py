import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_local_commercial_launcher_uses_isolated_loopback_production_runtime() -> None:
    script = (ROOT / "scripts" / "windows" / "veridra-commercial-local.ps1").read_text(
        encoding="utf-8"
    )

    assert "$env:VERIDRA_ENV = 'local'" in script
    assert "Remove-Item Env:VERIDRA_LOCAL_AGENCY" in script
    assert "$env:VERIDRA_BIND_HOST = '127.0.0.1'" in script
    assert "$StateRoot = Join-Path $env:LOCALAPPDATA 'VeridraCommercial'" in script
    assert "$env:VERIDRA_TRUSTED_ORIGIN = $Url.TrimEnd('/')" in script
    assert "Remove-Item Env:VERIDRA_LOCAL_AUTOLOGIN" in script
    assert "$env:VERIDRA_TENANT_DATA_ROOT = Join-Path $DataRoot 'tenants'" in script
    assert "veridra.monitoring_service" in script
    assert "veridra.crawl_worker_service" in script
    assert "http://127.0.0.1:$Port/" in script
    assert "0.0.0.0" not in script


def test_local_commercial_batch_launchers_target_dedicated_launcher() -> None:
    commands = {
        "VERIDRA_COMMERCIAL_OPEN.bat": "open",
        "VERIDRA_COMMERCIAL_START.bat": "start",
        "VERIDRA_COMMERCIAL_STOP.bat": "stop",
        "VERIDRA_COMMERCIAL_STATUS.bat": "status",
        "VERIDRA_COMMERCIAL_PREFLIGHT.bat": "preflight",
        "VERIDRA_COMMERCIAL_BACKUP.bat": "backup",
    }
    for filename, command in commands.items():
        body = (ROOT / filename).read_text(encoding="utf-8")
        assert "veridra-commercial-local.ps1" in body
        assert f" {command} %*" in body


def test_every_declared_local_commercial_command_is_dispatched() -> None:
    script = (ROOT / "scripts" / "windows" / "veridra-commercial-local.ps1").read_text(
        encoding="utf-8"
    )

    declared_match = re.search(
        r"\[ValidateSet\((.*?)\)\]\s*\[string\]\$Command",
        script,
        flags=re.DOTALL,
    )
    assert declared_match is not None
    declared = set(re.findall(r"'([^']+)'", declared_match.group(1)))
    dispatched = set(
        re.findall(r"^\s*'([^']+)'\s*\{\s*Invoke-", script, flags=re.MULTILINE)
    )

    assert declared == dispatched


def test_crawl_worker_service_is_bounded_and_uses_tenant_data_root() -> None:
    service = (ROOT / "src" / "veridra" / "crawl_worker_service.py").read_text(
        encoding="utf-8"
    )

    assert "VERIDRA_TENANT_DATA_ROOT" in service
    assert "--interval" in service
    assert "--limit" in service
    assert "CrawlWorker(root=root).run_once(limit=args.limit)" in service
    assert "time.sleep(args.interval)" in service


def test_launcher_rejects_reused_pid_files_and_rechecks_web_health() -> None:
    script = (ROOT / "scripts" / "windows" / "veridra-commercial-local.ps1").read_text(
        encoding="utf-8"
    )

    assert "Get-CimInstance Win32_Process" in script
    assert "ExpectedCommandLineFragment" in script
    assert "ProcessId = $processId" in script
    assert "Get-ManagedProcess $PidFile '-m veridra.runtime'" in script
    assert "Get-ManagedProcess $MonitoringPidFile '-m veridra.monitoring_service'" in script
    assert "Get-ManagedProcess $CrawlPidFile '-m veridra.crawl_worker_service'" in script
    assert "Stop-One 'web' $PidFile '-m veridra.runtime'" in script
    assert "Stop-One 'monitoring' $MonitoringPidFile '-m veridra.monitoring_service'" in script
    assert "Stop-One 'crawl worker' $CrawlPidFile '-m veridra.crawl_worker_service'" in script

    worker_start = script.index("Start-Worker 'crawl worker service'")
    ready = script.index('Write-Step "Ready at $Url"')
    wait_ready = script.rfind("Wait-Ready", worker_start, ready)
    assert wait_ready != -1


def test_local_launcher_describes_webify_mode_not_saas_plan_runtime() -> None:
    script = (ROOT / "scripts" / "windows" / "veridra-commercial-local.ps1").read_text(
        encoding="utf-8"
    )

    assert "Mode: Webify private local agency" in script
    assert "no VERIDRA SaaS plan/billing gate" in script
    assert "Legacy Stripe sandbox config" not in script


def test_local_launcher_contains_no_retired_saas_dispatches() -> None:
    script = (ROOT / "scripts" / "windows" / "veridra-commercial-local.ps1").read_text(
        encoding="utf-8"
    )
    for retired in (
        "Set-LegacyProviderEnvironment",
        "Import-StripeEnvironment",
        "Clear-StripeEnvironment",
        "Invoke-H6Phase3",
        "Invoke-ProviderSnapshot",
        "local_provider_snapshot",
        "local_provider_reconcile",
        "local_h6_acceptance",
        "/signup",
    ):
        assert retired not in script
    assert "Start-Process ($Url.TrimEnd('/') + '/agency')" in script


def test_data_audit_uses_isolated_restored_snapshot_not_live_sqlite() -> None:
    script = (ROOT / "scripts" / "windows" / "veridra-commercial-local.ps1").read_text(
        encoding="utf-8"
    )
    assert "'data-audit' { Invoke-DataAudit }" in script
    audit = script.split("function Invoke-DataAudit {", 1)[1].split("\nswitch ($Command)", 1)[0]
    assert "Invoke-Backup" in audit
    assert "Invoke-RecoveryTest" in audit
    assert "webify_data_inventory.py" in audit
    assert "--identity-db $identityDb --tenant-root $tenantRoot" in audit
    assert "WEBIFY_DATA_AUDIT_" in audit
    assert "identity.integrity -ne 'ok'" in audit


def test_commercial_setup_does_not_delegate_to_retired_operator_launcher() -> None:
    script = (ROOT / "scripts" / "windows" / "veridra-commercial-local.ps1").read_text(
        encoding="utf-8"
    )
    setup = script.split("function Ensure-Python {", 1)[1].split(
        "function Set-BaseCommercialEnvironment {", 1
    )[0]
    assert "veridra-local.ps1" not in setup
    assert "python -m venv" not in setup
    assert "-m venv" in setup
    assert '-m pip install -e "$RepoRoot[dev]"' in setup
    assert "-m playwright install chromium" in setup
    assert "if ($LASTEXITCODE -ne 0)" in setup


def test_release_check_certifies_preflight_backup_recovery_and_live_services() -> None:
    script = (ROOT / "scripts" / "windows" / "veridra-commercial-local.ps1").read_text(
        encoding="utf-8"
    )
    release = script.split("function Invoke-ReleaseCheck {", 1)[1].split(
        "\nswitch ($Command)", 1
    )[0]
    assert "Invoke-Preflight" in release
    assert "Invoke-DataAudit" in release
    assert "Invoke-Status" in release
    assert release.index("Invoke-Preflight") < release.index("Invoke-DataAudit")
    assert release.index("Invoke-DataAudit") < release.index("Invoke-Status")
    assert "'release-check' { Invoke-ReleaseCheck }" in script


def test_canonical_launcher_clears_legacy_agency_flag_before_runtime() -> None:
    script = (ROOT / "scripts" / "windows" / "veridra-commercial-local.ps1").read_text(
        encoding="utf-8"
    )
    assert "Remove-Item Env:VERIDRA_LOCAL_AGENCY -ErrorAction SilentlyContinue" in script
    assert "$env:VERIDRA_ENV = 'local'" in script


def test_legacy_state_check_is_read_only_and_reports_migration_blockers() -> None:
    script = (ROOT / "scripts" / "windows" / "veridra-commercial-local.ps1").read_text(
        encoding="utf-8"
    )
    check = script.split("function Invoke-LegacyStateCheck {", 1)[1].split(
        "\nswitch ($Command)", 1
    )[0]
    assert "'legacy-state-check' { Invoke-LegacyStateCheck }" in script
    assert "legacy_database_files" in check
    assert "legacy_backup_files" in check
    assert "migration_review_required" in check
    assert "Get-ChildItem" in check
    assert "Remove-Item" not in check
    assert "Move-Item" not in check
    assert "Copy-Item" not in check
