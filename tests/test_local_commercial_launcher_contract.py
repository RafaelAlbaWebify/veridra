import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_local_commercial_launcher_uses_isolated_loopback_production_runtime() -> None:
    script = (ROOT / "scripts" / "windows" / "veridra-commercial-local.ps1").read_text(
        encoding="utf-8"
    )

    assert "$env:VERIDRA_ENV = 'production'" in script
    assert "$env:VERIDRA_LOCAL_AGENCY = '1'" in script
    assert "$env:VERIDRA_BIND_HOST = '127.0.0.1'" in script
    assert "$StateRoot = Join-Path $env:LOCALAPPDATA 'VeridraCommercial'" in script
    assert "$env:VERIDRA_TRUSTED_ORIGIN = $Url.TrimEnd('/')" in script
    assert "Remove-Item Env:VERIDRA_LOCAL_AUTOLOGIN" in script
    assert "Clear-StripeEnvironment" in script
    assert "Set-LegacyProviderEnvironment" in script
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
        "VERIDRA_COMMERCIAL_H6_PHASE3.bat": "h6-phase3",
        "VERIDRA_COMMERCIAL_H6_PHASE4.bat": "h6-phase4",
        "VERIDRA_COMMERCIAL_H6_PHASE5.bat": "h6-phase5",
        "VERIDRA_COMMERCIAL_H6_PHASE6.bat": "h6-phase6",
    }
    for filename, command in commands.items():
        body = (ROOT / filename).read_text(encoding="utf-8")
        assert "veridra-commercial-local.ps1" in body
        assert f" {command} %*" in body


def test_local_commercial_tenant_launcher_is_read_only_helper() -> None:
    body = (ROOT / "VERIDRA_COMMERCIAL_TENANTS.bat").read_text(encoding="utf-8")
    script = (ROOT / "scripts" / "windows" / "veridra-commercial-local.ps1").read_text(
        encoding="utf-8"
    )

    assert "veridra-commercial-local.ps1" in body
    assert " tenants %*" in body
    assert "'tenants' { Invoke-Tenants }" in script
    assert "veridra.local_commercial_tenants" in script


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
    assert "Legacy Stripe sandbox config" in script


def test_normal_local_runtime_does_not_import_saas_stripe_secrets() -> None:
    script = (ROOT / "scripts" / "windows" / "veridra-commercial-local.ps1").read_text(
        encoding="utf-8"
    )

    start = script.index("function Set-CommercialEnvironment")
    legacy = script.index("function Set-LegacyProviderEnvironment")
    local_block = script[start:legacy]
    assert "Clear-StripeEnvironment" in local_block
    assert "Import-StripeEnvironment" not in local_block
    assert "VERIDRA_LOCAL_AGENCY = '1'" in local_block
