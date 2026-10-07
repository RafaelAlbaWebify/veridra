from __future__ import annotations

import argparse
from pathlib import Path

from .recovery_readiness import RecoveryReadinessError, validate_recovery_readiness


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate that an isolated VERIDRA restore contains representative "
            "#296 recovery-readiness evidence."
        )
    )
    parser.add_argument("--identity-db", required=True, type=Path)
    parser.add_argument("--tenant-data-root", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        summary = validate_recovery_readiness(
            identity_database=args.identity_db,
            tenant_data_root=args.tenant_data_root,
        )
    except RecoveryReadinessError as exc:
        print(f"recovery_readiness=FAIL detail={exc}")
        return 1
    print(
        "recovery_readiness=PASS "
        f"users={summary.users} "
        f"tenants={summary.tenants} "
        f"projects={summary.projects} "
        f"assessments={summary.assessments} "
        f"report_evidence={summary.report_evidence} "
        f"monitoring_jobs={summary.monitoring_jobs}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
