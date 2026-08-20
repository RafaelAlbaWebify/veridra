from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .version import __version__

_FORMAT_VERSION: Final[int] = 1
_IDENTITY_MEMBER: Final[str] = "identity/identity.sqlite3"
_EMAIL_PREFIX: Final[str] = "identity/identity-email-deliveries/"
_TENANT_PREFIX: Final[str] = "tenants/"
_MANIFEST_MEMBER: Final[str] = "manifest.json"


class BackupRestoreError(RuntimeError):
    pass


class SnapshotFile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str = Field(min_length=1, max_length=2048)
    size: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class SnapshotManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    format_version: int = Field(ge=1)
    created_at: datetime
    veridra_version: str = Field(min_length=1, max_length=100)
    consistency: str = Field(pattern=r"^operator_quiesced$")
    files: list[SnapshotFile]


@dataclass(frozen=True)
class BackupResult:
    archive: Path
    manifest: SnapshotManifest


@dataclass(frozen=True)
class RestoreResult:
    identity_database: Path
    tenant_data_root: Path
    restored_files: int


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_member_name(name: str) -> None:
    path = PurePosixPath(name)
    if (
        not name
        or path.is_absolute()
        or ".." in path.parts
        or "\\" in name
        or name.startswith("/")
    ):
        raise BackupRestoreError("Backup archive contains an unsafe path.")


def _check_sqlite(database: Path) -> None:
    if not database.is_file():
        raise BackupRestoreError("Identity database does not exist.")
    try:
        connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
        try:
            result = connection.execute("PRAGMA quick_check").fetchone()
        finally:
            connection.close()
    except sqlite3.Error as exc:
        raise BackupRestoreError("Identity database could not be validated.") from exc
    if result is None or result[0] != "ok":
        raise BackupRestoreError("Identity database failed SQLite integrity validation.")


def _sqlite_backup(source: Path, destination: Path) -> None:
    try:
        source_connection = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
        destination_connection = sqlite3.connect(destination)
        try:
            source_connection.backup(destination_connection)
        finally:
            destination_connection.close()
            source_connection.close()
    except sqlite3.Error as exc:
        raise BackupRestoreError("Identity database snapshot failed.") from exc
    _check_sqlite(destination)


def _iter_regular_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    if not root.is_dir() or root.is_symlink():
        raise BackupRestoreError("Backup source directory is invalid.")
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise BackupRestoreError("Backup source contains a symbolic link.")
        if path.is_file():
            files.append(path)
        elif not path.is_dir():
            raise BackupRestoreError("Backup source contains an unsupported filesystem entry.")
    return files


def _add_file(
    archive: zipfile.ZipFile,
    source: Path,
    member: str,
    entries: list[SnapshotFile],
) -> None:
    _validate_member_name(member)
    archive.write(source, member)
    entries.append(
        SnapshotFile(path=member, size=source.stat().st_size, sha256=_sha256(source))
    )


def create_backup(
    *,
    identity_database: Path,
    tenant_data_root: Path,
    output: Path,
    confirm_quiesced: bool,
    now: datetime | None = None,
) -> BackupResult:
    if not confirm_quiesced:
        raise BackupRestoreError(
            "Backup requires explicit confirmation that web, worker and billing writers are quiesced."
        )
    identity_database = identity_database.expanduser().resolve()
    tenant_data_root = tenant_data_root.expanduser().resolve()
    output = output.expanduser().resolve()
    _check_sqlite(identity_database)
    if not tenant_data_root.is_dir() or tenant_data_root.is_symlink():
        raise BackupRestoreError("Tenant data root does not exist or is invalid.")
    if output.exists():
        raise BackupRestoreError("Backup output already exists.")
    if output.is_relative_to(tenant_data_root) or output.is_relative_to(identity_database.parent):
        raise BackupRestoreError("Backup output must be outside durable source directories.")
    output.parent.mkdir(parents=True, exist_ok=True)

    timestamp = (now or datetime.now(UTC)).astimezone(UTC)
    entries: list[SnapshotFile] = []
    try:
        with tempfile.TemporaryDirectory(prefix="veridra-backup-") as temporary:
            temporary_root = Path(temporary)
            identity_snapshot = temporary_root / "identity.sqlite3"
            _sqlite_backup(identity_database, identity_snapshot)
            temporary_archive = output.with_name(f".{output.name}.{os.getpid()}.tmp")
            try:
                with zipfile.ZipFile(
                    temporary_archive,
                    "w",
                    compression=zipfile.ZIP_DEFLATED,
                    compresslevel=6,
                ) as archive:
                    _add_file(archive, identity_snapshot, _IDENTITY_MEMBER, entries)
                    email_root = identity_database.parent / "identity-email-deliveries"
                    for source in _iter_regular_files(email_root):
                        relative = source.relative_to(email_root).as_posix()
                        _add_file(archive, source, _EMAIL_PREFIX + relative, entries)
                    for source in _iter_regular_files(tenant_data_root):
                        relative = source.relative_to(tenant_data_root).as_posix()
                        _add_file(archive, source, _TENANT_PREFIX + relative, entries)
                    manifest = SnapshotManifest(
                        format_version=_FORMAT_VERSION,
                        created_at=timestamp,
                        veridra_version=__version__,
                        consistency="operator_quiesced",
                        files=sorted(entries, key=lambda entry: entry.path),
                    )
                    archive.writestr(
                        _MANIFEST_MEMBER,
                        json.dumps(
                            manifest.model_dump(mode="json"),
                            sort_keys=True,
                            separators=(",", ":"),
                        ).encode("utf-8"),
                    )
                temporary_archive.replace(output)
            finally:
                temporary_archive.unlink(missing_ok=True)
    except (OSError, zipfile.BadZipFile) as exc:
        output.unlink(missing_ok=True)
        raise BackupRestoreError("Backup archive could not be created safely.") from exc
    return BackupResult(archive=output, manifest=manifest)


def _load_and_verify_archive(archive_path: Path, staging: Path) -> SnapshotManifest:
    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise BackupRestoreError("Backup archive contains duplicate paths.")
            for name in names:
                _validate_member_name(name)
            if _MANIFEST_MEMBER not in names:
                raise BackupRestoreError("Backup archive has no manifest.")
            try:
                manifest = SnapshotManifest.model_validate_json(archive.read(_MANIFEST_MEMBER))
            except (KeyError, ValidationError, ValueError) as exc:
                raise BackupRestoreError("Backup manifest is invalid.") from exc
            if manifest.format_version != _FORMAT_VERSION:
                raise BackupRestoreError("Backup format version is not supported.")
            expected = {_MANIFEST_MEMBER, *(entry.path for entry in manifest.files)}
            if set(names) != expected:
                raise BackupRestoreError("Backup archive contents do not match the manifest.")
            if not any(entry.path == _IDENTITY_MEMBER for entry in manifest.files):
                raise BackupRestoreError("Backup archive is missing the identity database.")
            for entry in manifest.files:
                _validate_member_name(entry.path)
                destination = staging.joinpath(*PurePosixPath(entry.path).parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(entry.path, "r") as source, destination.open("wb") as target:
                    shutil.copyfileobj(source, target, length=1024 * 1024)
                if destination.stat().st_size != entry.size or _sha256(destination) != entry.sha256:
                    raise BackupRestoreError("Backup archive failed integrity verification.")
    except zipfile.BadZipFile as exc:
        raise BackupRestoreError("Backup archive is not a valid ZIP file.") from exc
    _check_sqlite(staging / _IDENTITY_MEMBER)
    return manifest


def _directory_nonempty(path: Path) -> bool:
    return path.exists() and (not path.is_dir() or any(path.iterdir()))


def restore_backup(
    *,
    archive: Path,
    identity_database: Path,
    tenant_data_root: Path,
    confirm_quiesced: bool,
    replace_existing: bool = False,
) -> RestoreResult:
    if not confirm_quiesced:
        raise BackupRestoreError(
            "Restore requires explicit confirmation that web, worker and billing writers are quiesced."
        )
    archive = archive.expanduser().resolve()
    identity_database = identity_database.expanduser().resolve()
    tenant_data_root = tenant_data_root.expanduser().resolve()
    if not archive.is_file():
        raise BackupRestoreError("Backup archive does not exist.")
    email_target = identity_database.parent / "identity-email-deliveries"
    if not replace_existing and (
        identity_database.exists()
        or _directory_nonempty(email_target)
        or _directory_nonempty(tenant_data_root)
    ):
        raise BackupRestoreError(
            "Restore targets already contain durable state; use explicit replacement only while quiesced."
        )

    identity_database.parent.mkdir(parents=True, exist_ok=True)
    tenant_data_root.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="veridra-restore-") as temporary:
        staging = Path(temporary)
        manifest = _load_and_verify_archive(archive, staging)
        staged_identity = staging / _IDENTITY_MEMBER
        staged_email = staging / _EMAIL_PREFIX.rstrip("/")
        staged_tenants = staging / _TENANT_PREFIX.rstrip("/")

        replacement_root = Path(tempfile.mkdtemp(prefix=".veridra-restore-", dir=tenant_data_root.parent))
        try:
            staged_tenant_copy = replacement_root / "tenants"
            if staged_tenants.exists():
                shutil.copytree(staged_tenants, staged_tenant_copy)
            else:
                staged_tenant_copy.mkdir()

            staged_identity_copy = identity_database.with_name(
                f".{identity_database.name}.{os.getpid()}.restore"
            )
            shutil.copy2(staged_identity, staged_identity_copy)
            staged_email_copy = identity_database.parent / f".identity-email-deliveries.{os.getpid()}.restore"
            if staged_email.exists():
                shutil.copytree(staged_email, staged_email_copy)

            if replace_existing:
                identity_database.unlink(missing_ok=True)
                if email_target.exists():
                    shutil.rmtree(email_target)
                if tenant_data_root.exists():
                    shutil.rmtree(tenant_data_root)
            staged_identity_copy.replace(identity_database)
            if staged_email_copy.exists():
                staged_email_copy.replace(email_target)
            staged_tenant_copy.replace(tenant_data_root)
        except OSError as exc:
            raise BackupRestoreError("Restore could not replace durable state safely.") from exc
        finally:
            shutil.rmtree(replacement_root, ignore_errors=True)
            for candidate in identity_database.parent.glob(".*.restore"):
                if candidate.is_dir():
                    shutil.rmtree(candidate, ignore_errors=True)
                else:
                    candidate.unlink(missing_ok=True)

    _check_sqlite(identity_database)
    return RestoreResult(
        identity_database=identity_database,
        tenant_data_root=tenant_data_root,
        restored_files=len(manifest.files),
    )
