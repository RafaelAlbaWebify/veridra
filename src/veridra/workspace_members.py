from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from tempfile import NamedTemporaryFile

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from .workspace_policy import PLAN_CATALOGUE, WorkspaceConfig


class MemberStoreError(RuntimeError):
    pass


class MemberRole(StrEnum):
    owner = "owner"
    administrator = "administrator"
    analyst = "analyst"
    sales = "sales"
    viewer = "viewer"


class Capability(StrEnum):
    manage_workspace = "manage_workspace"
    manage_members = "manage_members"
    manage_projects = "manage_projects"
    run_assessments = "run_assessments"
    manage_reports = "manage_reports"
    manage_leads = "manage_leads"
    manage_monitoring = "manage_monitoring"
    manage_tasks = "manage_tasks"
    view_data = "view_data"


ROLE_CAPABILITIES: dict[MemberRole, frozenset[Capability]] = {
    MemberRole.owner: frozenset(Capability),
    MemberRole.administrator: frozenset(Capability),
    MemberRole.analyst: frozenset(
        {
            Capability.manage_projects,
            Capability.run_assessments,
            Capability.manage_reports,
            Capability.manage_monitoring,
            Capability.manage_tasks,
            Capability.view_data,
        }
    ),
    MemberRole.sales: frozenset(
        {
            Capability.manage_leads,
            Capability.manage_reports,
            Capability.view_data,
        }
    ),
    MemberRole.viewer: frozenset({Capability.view_data}),
}


class WorkspaceMember(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    id: str = Field(min_length=24, max_length=24, pattern=r"^[0-9a-f]{24}$")
    display_name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    role: MemberRole
    active: bool = True
    created_at: datetime
    updated_at: datetime

    @classmethod
    def build(
        cls,
        *,
        display_name: str,
        email: str,
        role: MemberRole,
        active: bool = True,
        now: datetime | None = None,
    ) -> WorkspaceMember:
        timestamp = (now or datetime.now(UTC)).astimezone(UTC)
        seed = json.dumps(
            {"display_name": display_name.strip(), "email": email.strip().lower()},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return cls(
            id=hashlib.sha256(seed).hexdigest()[:24],
            display_name=display_name,
            email=email.lower(),
            role=role,
            active=active,
            created_at=timestamp,
            updated_at=timestamp,
        )

    def can(self, capability: Capability) -> bool:
        return self.active and capability in ROLE_CAPABILITIES[self.role]


class AuditEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    action: str = Field(min_length=1, max_length=120)
    occurred_at: datetime
    actor_member_id: str = Field(default="", max_length=24)
    subject_type: str = Field(min_length=1, max_length=80)
    subject_id: str = Field(default="", max_length=120)
    detail: str = Field(default="", max_length=500)


def default_members_directory() -> Path:
    configured = os.environ.get("VERIDRA_DATA_DIR")
    root = Path(configured).expanduser().resolve() if configured else Path.home() / ".veridra"
    return root / "members"


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        mode="wb",
        dir=path.parent,
        prefix=f".{path.stem}.",
        suffix=".tmp",
        delete=False,
    ) as temporary:
        temporary.write(content)
        temporary.flush()
        os.fsync(temporary.fileno())
        temporary_path = Path(temporary.name)
    temporary_path.replace(path)


class MemberStore:
    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or default_members_directory()

    def list(self) -> list[WorkspaceMember]:
        if not self.directory.exists():
            return []
        members: list[WorkspaceMember] = []
        for path in sorted(self.directory.glob("*.json")):
            try:
                members.append(
                    WorkspaceMember.model_validate_json(path.read_text(encoding="utf-8"))
                )
            except (OSError, ValueError):
                continue
        return sorted(members, key=lambda member: (member.display_name.casefold(), member.id))

    def load(self, member_id: str) -> WorkspaceMember:
        path = self.directory / f"{member_id}.json"
        if not path.exists():
            raise MemberStoreError("Workspace member was not found.")
        try:
            return WorkspaceMember.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise MemberStoreError("Workspace member could not be read safely.") from exc

    def save(self, member: WorkspaceMember, workspace: WorkspaceConfig) -> str:
        existing = {item.id: item for item in self.list()}
        active_count = sum(1 for item in existing.values() if item.active)
        prior = existing.get(member.id)
        activating = member.active and (prior is None or not prior.active)
        seat_limit = PLAN_CATALOGUE[workspace.plan].max_users
        if activating and active_count >= seat_limit:
            raise MemberStoreError("The active workspace plan seat allowance is exhausted.")
        self._validate_owner_invariant(existing, replacement=member)
        content = json.dumps(
            member.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        _atomic_write(self.directory / f"{member.id}.json", content)
        return member.id

    def delete(self, member_id: str) -> None:
        existing = {item.id: item for item in self.list()}
        member = existing.get(member_id)
        if member is None:
            raise MemberStoreError("Workspace member was not found.")
        if member.active and member.role == MemberRole.owner and not any(
            item.id != member_id and item.active and item.role == MemberRole.owner
            for item in existing.values()
        ):
            raise MemberStoreError("At least one active workspace owner is required.")
        (self.directory / f"{member_id}.json").unlink()

    @staticmethod
    def _validate_owner_invariant(
        existing: dict[str, WorkspaceMember],
        *,
        replacement: WorkspaceMember | None = None,
    ) -> None:
        candidate = dict(existing)
        if replacement is not None:
            candidate[replacement.id] = replacement
        if candidate and not any(
            member.active and member.role == MemberRole.owner
            for member in candidate.values()
        ):
            raise MemberStoreError("At least one active workspace owner is required.")


class AuditTrailStore:
    def __init__(self, directory: Path | None = None) -> None:
        root = directory or default_members_directory()
        self.directory = root / "audit"

    def record(self, event: AuditEvent) -> str:
        content = json.dumps(
            event.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        identifier = hashlib.sha256(content).hexdigest()[:24]
        destination = self.directory / f"{identifier}.json"
        if not destination.exists():
            _atomic_write(destination, content)
        return identifier

    def list(self) -> list[tuple[str, AuditEvent]]:
        if not self.directory.exists():
            return []
        events: list[tuple[str, AuditEvent]] = []
        for path in sorted(self.directory.glob("*.json")):
            try:
                event = AuditEvent.model_validate_json(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            events.append((path.stem, event))
        return sorted(events, key=lambda item: (item[1].occurred_at, item[0]), reverse=True)
