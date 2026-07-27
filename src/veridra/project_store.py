from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from .core import normalize_url
from .crawl_profiles import CrawlProfile, CrawlProfileName, resolve_crawl_profile
from .monitoring_schedule import MonitoringCadence, MonitoringSchedule


class ProjectStoreError(RuntimeError):
    pass


class ClientProject(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=120)
    target_url: str = Field(min_length=1, max_length=2048)
    client_label: str | None = Field(default=None, max_length=120)
    contact_label: str | None = Field(default=None, max_length=120)
    contact_member_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{24}$")
    profile_id: str | None = Field(default=None, min_length=24, max_length=24)
    crawl_profile: CrawlProfileName = CrawlProfileName.quick
    crawl_max_pages: int | None = None
    crawl_max_depth: int | None = None
    crawl_max_total_bytes: int | None = None
    crawl_per_page_bytes: int | None = None
    crawl_timeout: float | None = None
    crawl_max_sitemaps: int | None = None
    crawl_max_sitemap_urls: int | None = None
    monitoring_schedule: MonitoringSchedule = Field(default_factory=MonitoringSchedule)
    monitoring_email: EmailStr | None = None

    @classmethod
    def build(
        cls,
        *,
        name: str,
        target_url: str,
        client_label: str | None = None,
        contact_label: str | None = None,
        contact_member_id: str | None = None,
        profile_id: str | None = None,
        crawl_profile: str | CrawlProfileName = CrawlProfileName.quick,
        crawl_max_pages: int | None = None,
        crawl_max_depth: int | None = None,
        crawl_max_total_bytes: int | None = None,
        crawl_per_page_bytes: int | None = None,
        crawl_timeout: float | None = None,
        crawl_max_sitemaps: int | None = None,
        crawl_max_sitemap_urls: int | None = None,
        monitoring_schedule: MonitoringSchedule | None = None,
        monitoring_email: str | None = None,
    ) -> ClientProject:
        resolved = resolve_crawl_profile(
            crawl_profile,
            max_pages=crawl_max_pages,
            max_depth=crawl_max_depth,
            max_total_bytes=crawl_max_total_bytes,
            per_page_bytes=crawl_per_page_bytes,
            timeout=crawl_timeout,
            max_sitemaps=crawl_max_sitemaps,
            max_sitemap_urls=crawl_max_sitemap_urls,
        )
        custom = resolved.name == CrawlProfileName.custom
        return cls(
            name=name,
            target_url=normalize_url(target_url),
            client_label=client_label,
            contact_label=contact_label,
            contact_member_id=contact_member_id,
            profile_id=profile_id,
            crawl_profile=resolved.name,
            crawl_max_pages=resolved.limits.max_pages if custom else None,
            crawl_max_depth=resolved.limits.max_depth if custom else None,
            crawl_max_total_bytes=(resolved.limits.max_total_bytes if custom else None),
            crawl_per_page_bytes=(resolved.limits.per_page_bytes if custom else None),
            crawl_timeout=resolved.limits.timeout if custom else None,
            crawl_max_sitemaps=resolved.limits.max_sitemaps if custom else None,
            crawl_max_sitemap_urls=(resolved.limits.max_sitemap_urls if custom else None),
            monitoring_schedule=monitoring_schedule or MonitoringSchedule(),
            monitoring_email=monitoring_email,
        )

    def resolved_crawl_profile(self) -> CrawlProfile:
        return resolve_crawl_profile(
            self.crawl_profile,
            max_pages=self.crawl_max_pages,
            max_depth=self.crawl_max_depth,
            max_total_bytes=self.crawl_max_total_bytes,
            per_page_bytes=self.crawl_per_page_bytes,
            timeout=self.crawl_timeout,
            max_sitemaps=self.crawl_max_sitemaps,
            max_sitemap_urls=self.crawl_max_sitemap_urls,
        )


@dataclass(frozen=True)
class ProjectEntry:
    id: str
    name: str
    target_url: str
    client_label: str | None
    contact_label: str | None
    contact_member_id: str | None
    profile_id: str | None
    crawl_profile: CrawlProfileName
    monitoring_cadence: MonitoringCadence
    monitoring_email: str | None


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

    def _write(self, entry_id: str, project: ClientProject) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
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

    def save(self, project: ClientProject) -> str:
        entry_id = project_id(project)
        self._write(entry_id, project)
        return entry_id

    def overwrite(self, entry_id: str, project: ClientProject) -> str:
        current = self._path(entry_id)
        if not current.exists():
            raise ProjectStoreError("Saved project was not found.")
        self._write(entry_id, project)
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
                    contact_label=project.contact_label,
                    contact_member_id=project.contact_member_id,
                    profile_id=project.profile_id,
                    crawl_profile=project.crawl_profile,
                    monitoring_cadence=project.monitoring_schedule.cadence,
                    monitoring_email=(
                        str(project.monitoring_email)
                        if project.monitoring_email is not None
                        else None
                    ),
                )
            )
        return sorted(entries, key=lambda item: (item.name.lower(), item.id))

    def delete(self, entry_id: str) -> None:
        try:
            self._path(entry_id).unlink()
        except FileNotFoundError as exc:
            raise ProjectStoreError("Saved project was not found.") from exc
