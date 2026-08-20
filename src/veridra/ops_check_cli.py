from __future__ import annotations

import argparse
import os
from datetime import timedelta
from pathlib import Path

from .ops_check import OpsCheckConfig, OpsCheckError, report_json, run_ops_check


def _path(explicit: Path | None, environment_name: str) -> Path:
    configured = os.environ.get(environment_name)
    value = explicit or (Path(configured) if configured else None)
    if value is None:
        raise OpsCheckError(
            f"Required path is missing; provide the CLI option or {environment_name}."
        )
    return value.expanduser().resolve()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run a non-public Veridra production operations check and emit stable JSON. "
            "Exit codes: 0 ok, 1 warning, 2 critical."
        )
    )
    parser.add_argument("--identity-db", type=Path, default=None)
    parser.add_argument("--tenant-data-root", type=Path, default=None)
    parser.add_argument("--backup-dir", type=Path, default=None)
    parser.add_argument("--recent-hours", type=float, default=24.0)
    parser.add_argument("--queued-overdue-minutes", type=float, default=30.0)
    parser.add_argument("--backup-max-age-hours", type=float, default=26.0)
    return parser


def main() -> None:
    args = _parser().parse_args()
    try:
        report = run_ops_check(
            OpsCheckConfig(
                identity_database=_path(args.identity_db, "VERIDRA_IDENTITY_DB"),
                tenant_data_root=_path(
                    args.tenant_data_root,
                    "VERIDRA_TENANT_DATA_ROOT",
                ),
                recent_window=timedelta(hours=args.recent_hours),
                queued_overdue=timedelta(minutes=args.queued_overdue_minutes),
                backup_directory=(
                    args.backup_dir.expanduser().resolve() if args.backup_dir else None
                ),
                backup_max_age=timedelta(hours=args.backup_max_age_hours),
            )
        )
    except (OpsCheckError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    print(report_json(report))
    raise SystemExit(report.exit_code)


if __name__ == "__main__":
    main()
