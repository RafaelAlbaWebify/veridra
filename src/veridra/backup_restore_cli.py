from __future__ import annotations

import argparse
import os
from pathlib import Path

from .backup_restore import BackupRestoreError, create_backup, restore_backup


def _configured_path(explicit: Path | None, environment_name: str) -> Path:
    value = explicit or (Path(os.environ[environment_name]) if os.environ.get(environment_name) else None)
    if value is None:
        raise BackupRestoreError(
            f"Required path is missing; provide the CLI option or {environment_name}."
        )
    return value.expanduser().resolve()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Create or restore a verified Veridra durable-state snapshot. "
            "The command requires an explicit operator assertion that all writers are quiesced."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    backup = subparsers.add_parser("backup", help="Create a verified quiesced snapshot.")
    backup.add_argument("--output", type=Path, required=True)
    backup.add_argument("--identity-db", type=Path, default=None)
    backup.add_argument("--tenant-data-root", type=Path, default=None)
    backup.add_argument(
        "--confirm-quiesced",
        action="store_true",
        help="Assert that web, monitoring-worker and billing writers are stopped/quiesced.",
    )

    restore = subparsers.add_parser("restore", help="Restore and verify a snapshot.")
    restore.add_argument("--archive", type=Path, required=True)
    restore.add_argument("--identity-db", type=Path, default=None)
    restore.add_argument("--tenant-data-root", type=Path, default=None)
    restore.add_argument(
        "--confirm-quiesced",
        action="store_true",
        help="Assert that web, monitoring-worker and billing writers are stopped/quiesced.",
    )
    restore.add_argument(
        "--replace-existing",
        action="store_true",
        help="Explicitly permit replacement of existing durable state.",
    )
    return parser


def main() -> None:
    args = _parser().parse_args()
    try:
        identity_database = _configured_path(args.identity_db, "VERIDRA_IDENTITY_DB")
        tenant_data_root = _configured_path(
            args.tenant_data_root,
            "VERIDRA_TENANT_DATA_ROOT",
        )
        if args.command == "backup":
            result = create_backup(
                identity_database=identity_database,
                tenant_data_root=tenant_data_root,
                output=args.output,
                confirm_quiesced=args.confirm_quiesced,
            )
            print(
                f"backup={result.archive} files={len(result.manifest.files)} "
                f"created_at={result.manifest.created_at.isoformat()}"
            )
            return
        result = restore_backup(
            archive=args.archive,
            identity_database=identity_database,
            tenant_data_root=tenant_data_root,
            confirm_quiesced=args.confirm_quiesced,
            replace_existing=args.replace_existing,
        )
        print(
            f"restored_files={result.restored_files} "
            f"identity_db={result.identity_database} tenant_root={result.tenant_data_root}"
        )
    except BackupRestoreError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
