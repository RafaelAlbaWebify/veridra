from pathlib import Path

from pytest import MonkeyPatch

from veridra import dublin_acquisition_batch_resilient_cli as cli


def test_discovery_variant_retries_selector_failure(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[list[str]] = []
    outcomes = iter([2, 0])

    def fake_run(argv: list[str]) -> int:
        calls.append(argv)
        return next(outcomes)

    monkeypatch.setattr(cli, "discovery_run", fake_run)

    assert cli._run_discovery_variant(
        query="dentist in Dublin, IE",
        workdir=tmp_path,
        per_query_results=20,
        max_scrolls=14,
        max_seconds=75.0,
        retries=2,
        startup_wait_seconds=8.0,
    )
    assert len(calls) == 2
    assert calls[0][calls[0].index("--startup-wait-seconds") + 1] == "8.0"
    assert calls[1][calls[1].index("--startup-wait-seconds") + 1] == "12.0"


def test_discovery_variant_skips_after_retry_budget(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(cli, "discovery_run", lambda _argv: 2)

    assert not cli._run_discovery_variant(
        query="dentist in Dublin, IE",
        workdir=tmp_path,
        per_query_results=20,
        max_scrolls=14,
        max_seconds=75.0,
        retries=1,
        startup_wait_seconds=8.0,
    )
