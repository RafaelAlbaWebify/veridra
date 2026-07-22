from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile

from pydantic import BaseModel, ConfigDict, Field

from .core import normalize_url
from .crawl_profiles import CrawlProfile, CrawlProfileName, resolve_crawl_profile


class ProjectStoreError(RuntimeError):
    pass


class ClientProject(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=120)
    target_url: str = Field(min_length=1, max_length=2048)
    client_label: str | None = Field(default=None, max_length=120)
    profile_id: str | None = Field(default=None, min_length=24, max_length=24)
    crawl_profile: CrawlProfileName = CrawlProfileName.quick
    crawl_max_pages: int | None = None
    crawl_max_depth: int | None = None

    @classmethod
    def build(
        cls,
        *,
        name: str,
        target_url: str,
        client_label: str | None = None,
        profile_id: str | None = None,
        crawl_profile: str | CrawlProfileName = CrawlProfileName.quick,
        crawl_max_pages: int | None = None,
        crawl_max_depth: int | None = None,
    ) -> ClientProject:
        resolved = resolve_crawl_profile(
            crawl_profile,
            max_pages=crawl_max_pages,
            max_depth=crawl_max_depth,
        )
        return cls(
            name=name,
            target_url=normalize_url(target_url),
            client_label=client_label,
            profile_id=profile_id,
            crawl_profile=resolved.name,
            crawl_max_pages=(
                resolved.limits.max_pages if resolved.name == CrawlProfileName.custom else None
            ),
            crawl_max_depth=(
                resolved.limits.max_depth if resolved.name == CrawlProfileName.custom else None
            ),
        )

    def resolved_crawl_profile(self) -> CrawlProfile:
        return resolve_crawl_profile(
            self.crawl_profile,
            max_pages=self.crawl_max_pages,
            max_depth=self.crawl_max_depth,
        )


@dataclass(frozen=True)
class ProjectEntry:
    id: str
    name: str
    target_url: str
    client_label: str | None
    profile_id: str | None
    crawl_profile: CrawlProfileName


def default_project_directory() -> Path:
    configured = os.environ.get("VERIDRA_DATA_DIR")
    if configured:
        return Path(configured).expanduser().resolve() / "projects"
    return Path.home() / ".veridra" / "projects"


def _canonical_bytes(project: ClientProject) -> bytes:
    return json.dumps(
        project.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def project_id(project: ClientProject) -> str:
    return hashlib.sha256(_canonical_bytes(project)).hexdigest()[:24]


class ProjectStore:
    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or default_project_directory()

    def _path(self, entry_id: str) -> Path:
        valid = len(entry_id) == 24 and all(
            character in "0123456789abcdef" for character in entry_id
        )
        if not valid:
            raise ProjectStoreError("Invalid project identifier.")
        return self.directory / f"{entry_id}.json"

    def save(self, project: ClientProject) -> str:
        self.directory.mkdir(parents=True, exist_ok=True)
        entry_id = project_id(project)
        destination = self._path(entry_id)
        with NamedTemporaryFile(
            mode="wb",
            dir=self.directory,
            prefix=f".{entry_id}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(_canonical_bytes(project))
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        temporary_path.replace(destination)
        return entry_id

    def replace(self, entry_id: str, project: ClientProject) -> str:
        current = self._path(entry_id)
        if not current.exists():
            raise ProjectStoreError("Saved project was not found.")
        new_id = self.save(project)
        if new_id != entry_id:
            current.unlink()
        return new_id

    def load(self, entry_id: str) -> ClientProject:
        try:
            return ClientProject.model_validate_json(
                self._path(entry_id).read_text(encoding="utf-8")
            )
        except FileNotFoundError as exc:
            raise ProjectStoreError("Saved project was not found.") from exc
        except (OSError, ValueError) as exc:
            raise ProjectStoreError("Saved project could not be read safely.") from exc

    def list(self) -> list[ProjectEntry]:
        if not self.directory.exists():
            return []
        entries: list[ProjectEntry] = []
        for path in sorted(self.directory.glob("*.json")):
            try:
                project = ClientProject.model_validate_json(
                    path.read_text(encoding="utf-8")
                )
            except (OSError, ValueError):
                continue
            entries.append(
                ProjectEntry(
                    id=path.stem,
                    name=project.name,
                    target_url=project.target_url,
                    client_label=project.client_label,
                    profile_id=project.profile_id,
                    crawl_profile=project.crawl_profile,
                )
            )
        return sorted(entries, key=lambda item: (item.name.lower(), item.id))

    def delete(self, entry_id: str) -> None:
        try:
            self._path(entry_id).unlink()
        except FileNotFoundError as exc:
            raise ProjectStoreError("Saved project was not found.") from exc
