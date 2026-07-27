from __future__ import annotations

import argparse
import getpass
from pathlib import Path

from .identity_bootstrap import (
    BOOTSTRAP_CONFIRMATION,
    IdentityBootstrapError,
    SQLiteIdentityBootstrap,
)
from .tenant_project_store import default_tenant_data_directory


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="veridra-identity-bootstrap",
        description="Create the first Veridra tenant owner in an empty identity database.",
    )
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument(
        "--tenant-data-root",
        type=Path,
        help=(
            "Tenant data directory. Defaults to the configured Veridra tenant data "
            "directory. The initial free workspace is created here."
        ),
    )
    parser.add_argument("--tenant-slug", required=True)
    parser.add_argument("--tenant-name", required=True)
    parser.add_argument("--owner-email", required=True)
    parser.add_argument("--owner-name", required=True)
    parser.add_argument(
        "--confirm",
        required=True,
        help=f"Required destructive confirmation token: {BOOTSTRAP_CONFIRMATION}",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    password = getpass.getpass("Owner password: ")
    confirmation = getpass.getpass("Repeat owner password: ")
    if password != confirmation:
        print("Passwords do not match.")
        return 2
    tenant_data_root = (
        args.tenant_data_root.expanduser().resolve()
        if args.tenant_data_root is not None
        else default_tenant_data_directory()
    )
    try:
        result = SQLiteIdentityBootstrap(
            args.database.expanduser().resolve(),
            tenant_data_root=tenant_data_root,
        ).create_first_owner(
            tenant_slug=args.tenant_slug,
            tenant_name=args.tenant_name,
            owner_email=args.owner_email,
            owner_name=args.owner_name,
            password=password,
            confirmation=args.confirm,
        )
    except (IdentityBootstrapError, ValueError) as exc:
        print(f"Bootstrap failed: {exc}")
        return 1
    print(
        "Bootstrap complete: "
        f"tenant={result.tenant_slug} tenant_id={result.tenant_id} "
        f"owner={result.email} user_id={result.user_id}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
