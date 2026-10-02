from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_local_commercial_launcher_uses_isolated_loopback_production_runtime() -> None:
    script = (ROOT / "scripts" / "windows" / "veridra-commercial-local.ps1").read_text(
        encoding="utf-8"
    )

    assert "$env:VERIDRA_ENV = 'production'" in script
    assert "$env:VERIDRA_BIND_HOST = '127.0.0.1'" in script
    assert "$StateRoot = Join-Path $env:LOCALAPPDATA 'VeridraCommercial'" in script
    assert "$env:VERIDRA_TRUSTED_ORIGIN = $Url.TrimEnd('/')" in script
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


def test_crawl_worker_service_is_bounded_and_uses_tenant_data_root() -> None:
    service = (ROOT / "src" / "veridra" / "crawl_worker_service.py").read_text(
        encoding="utf-8"
    )

    assert "VERIDRA_TENANT_DATA_ROOT" in service
    assert "--interval" in service
    assert "--limit" in service
    assert "CrawlWorker(root=root).run_once(limit=args.limit)" in service
    assert "time.sleep(args.interval)" in service
