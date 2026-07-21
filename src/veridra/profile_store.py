from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile

from .report_profiles import ReportProfile


class ProfileStoreError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProfileEntry:
    id: str
    organisation_name: str
    client_name: str | None
    consultant_name: str | None


def default_profile_directory() -> Path:
    configured = os.environ.get("VERIDRA_DATA_DIR")
    if configured:
        return Path(configured).expanduser().resolve() / "profiles"
    return Path.home() / ".veridra" / "profiles"


def _canonical_bytes(profile: ReportProfile) -> bytes:
    return json.dumps(
        profile.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def profile_id(profile: ReportProfile) -> str:
    return hashlib.sha256(_canonical_bytes(profile)).hexdigest()[:24]


class ProfileStore:
    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or default_profile_directory()

    def _path(self, entry_id: str) -> Path:
        valid = len(entry_id) == 24 and all(
            character in "0123456789abcdef" for character in entry_id
        )
        if not valid:
            raise ProfileStoreError("Invalid profile identifier.")
        return self.directory / f"{entry_id}.json"

    def save(self, profile: ReportProfile) -> str:
        self.directory.mkdir(parents=True, exist_ok=True)
        entry_id = profile_id(profile)
        destination = self._path(entry_id)
        content = _canonical_bytes(profile)
        with NamedTemporaryFile(
            mode="wb",
            dir=self.directory,
            prefix=f".{entry_id}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        temporary_path.replace(destination)
        return entry_id

    def load(self, entry_id: str) -> ReportProfile:
        path = self._path(entry_id)
        try:
            return ReportProfile.model_validate_json(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ProfileStoreError("Saved profile was not found.") from exc
        except (OSError, ValueError) as exc:
            raise ProfileStoreError("Saved profile could not be read safely.") from exc

    def list(self) -> list[ProfileEntry]:
        if not self.directory.exists():
            return []
        entries: list[ProfileEntry] = []
        for path in sorted(self.directory.glob("*.json")):
            try:
                profile = ReportProfile.model_validate_json(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            entries.append(
                ProfileEntry(
                    id=path.stem,
                    organisation_name=profile.organisation_name,
                    client_name=profile.client_name,
                    consultant_name=profile.consultant_name,
                )
            )
        return sorted(entries, key=lambda item: (item.organisation_name.lower(), item.id))

    def delete(self, entry_id: str) -> None:
        try:
            self._path(entry_id).unlink()
        except FileNotFoundError as exc:
            raise ProfileStoreError("Saved profile was not found.") from exc
