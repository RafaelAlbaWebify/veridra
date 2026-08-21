from __future__ import annotations

import argparse
import os
from pathlib import Path

from .tenant_offboarding import TenantOffboardingError, offboard_tenant


def _configured_path(explicit: Path | None, environment_name: str) -> Path:
    value = explicit or (Path(os.environ[environment_name]) if os.environ.get(environment_name) else None)
    if value is None:
        raise TenantOffboardingError(
            f"Required path is missing; provide the CLI option or {environment_name}."
        )
    return value.expanduser().resolve()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Remove one Veridra tenant context after creating a verified recovery backup. "
            "User accounts are preserved because they may belong to other tenants."
        )
    )
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--backup-output", type=Path, required=True)
    parser.add_argument("--identity-db", type=Path, default=None)
    parser.add_argument("--tenant-data-root", type=Path, default=None)
    parser.add_argument(
        "--confirm-quiesced",
        action="store_true",
        help="Assert that web, monitoring-worker and billing writers are stopped/quiesced.",
    )
    parser.add_argument(
        "--confirm-provider-billing-handled",
        action="store_true",
        help=(
            "Assert that any provider-side Stripe subscription has already been cancelled, "
            "transferred or otherwise handled. Required only when a Stripe binding exists."
        ),
    )
    return parser


def main() -> None:
    args = _parser().parse_args()
    try:
        result = offboard_tenant(
            identity_database=_configured_path(args.identity_db, "VERIDRA_IDENTITY_DB"),
            tenant_data_root=_configured_path(
                args.tenant_data_root,
                "VERIDRA_TENANT_DATA_ROOT",
            ),
            tenant_id=args.tenant_id,
            backup_output=args.backup_output,
            confirm_quiesced=args.confirm_quiesced,
            confirm_provider_billing_handled=args.confirm_provider_billing_handled,
        )
    except TenantOffboardingError as exc:
        raise SystemExit(str(exc)) from exc
    print(
        f"tenant={result.tenant_id} backup={result.backup_archive} "
        f"sessions={result.deleted_sessions} invitations={result.deleted_invitations} "
        f"memberships={result.deleted_memberships} monitoring_jobs={result.deleted_monitoring_jobs}"
    )


if __name__ == "__main__":
    main()
