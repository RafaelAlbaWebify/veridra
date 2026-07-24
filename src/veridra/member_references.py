from __future__ import annotations

from .workspace_members import MemberStore, MemberStoreError


class MemberReferenceError(ValueError):
    pass


def require_active_member(
    member_id: str | None,
    *,
    store: MemberStore | None = None,
) -> str | None:
    if member_id is None:
        return None
    members = store or MemberStore()
    try:
        member = members.load(member_id)
    except MemberStoreError as exc:
        raise MemberReferenceError("Selected workspace member was not found.") from exc
    if not member.active:
        raise MemberReferenceError("Selected workspace member is inactive.")
    return member.id


def member_reference_label(
    member_id: str | None,
    legacy_label: str | None,
    *,
    store: MemberStore | None = None,
) -> str:
    fallback = (legacy_label or "").strip()
    if member_id is None:
        return fallback
    members = store or MemberStore()
    try:
        member = members.load(member_id)
    except MemberStoreError:
        return fallback
    if not member.active:
        return fallback
    return member.display_name
