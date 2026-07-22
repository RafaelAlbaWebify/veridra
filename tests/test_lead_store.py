# ruff: noqa: I001
from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from veridra.lead_store import (
    AuditLead,
    LeadFormConfig,
    LeadFormStore,
    LeadStatus,
    LeadStore,
    LeadStoreError,
)


FORM_ID = "a" * 24
ASSESSMENT_ID = "b" * 24


def _assert_raises(expected: type[Exception], operation: Callable[[], object]) -> None:
    try:
        operation()
    except expected:
        return
    raise AssertionError(f"Expected {expected.__name__} to be raised.")


def _form() -> LeadFormConfig:
    return LeadFormConfig(
        organisation_label="Example Agency",
        consent_text="I agree that Example Agency may contact me about this audit.",
        allowed_origins=(
            "https://www.example.com/path",
            "https://www.example.com/other",
            "https://client.example:8443/embed",
        ),
    )


def _lead(*, status: LeadStatus = LeadStatus.new) -> AuditLead:
    return AuditLead(
        form_id=FORM_ID,
        website="https://example.com",
        name="Rafael Alba",
        email="rafael@example.com",
        company="Example Ltd",
        consent_text="I agree that Example Agency may contact me about this audit.",
        consented_at=datetime(2026, 7, 21, 12, 0, tzinfo=UTC),
        assessment_id=ASSESSMENT_ID,
        status=status,
    )


def test_form_store_normalizes_origins_and_persists_atomically(tmp_path: Path) -> None:
    store = LeadFormStore(tmp_path / "forms")
    identifier = store.save(_form())
    loaded = store.load_form(identifier)

    assert len(identifier) == 24
    assert loaded.allowed_origins == (
        "https://client.example:8443",
        "https://www.example.com",
    )
    assert store.save(_form()) == identifier
    assert len(store.list()) == 1


def test_lead_store_supports_status_filter_replace_and_delete(tmp_path: Path) -> None:
    store = LeadStore(tmp_path / "records")
    identifier = store.save(_lead())

    assert store.load_lead(identifier).status == LeadStatus.new
    assert len(store.list_leads(form_id=FORM_ID, status=LeadStatus.new)) == 1
    assert store.list_leads(status=LeadStatus.won) == []

    replacement = _lead(status=LeadStatus.qualified)
    replacement_id = store.replace(identifier, replacement)
    assert replacement_id != identifier
    assert store.load_lead(replacement_id).status == LeadStatus.qualified
    _assert_raises(LeadStoreError, lambda: store.load_lead(identifier))

    store.delete(replacement_id)
    assert store.list_leads() == []


def test_lead_models_reject_invalid_email_unknown_fields_and_bad_ids() -> None:
    _assert_raises(
        ValueError,
        lambda: AuditLead(
            form_id=FORM_ID,
            website="https://example.com",
            name="Rafael",
            email="not-an-email",
            consent_text="Consent",
            consented_at=datetime.now(UTC),
            assessment_id=ASSESSMENT_ID,
        ),
    )
    _assert_raises(
        ValueError,
        lambda: LeadFormConfig(
            organisation_label="Agency",
            consent_text="Consent",
            unexpected="not allowed",
        ),
    )
    _assert_raises(
        ValueError,
        lambda: AuditLead(
            form_id="invalid",
            website="https://example.com",
            name="Rafael",
            email="rafael@example.com",
            consent_text="Consent",
            consented_at=datetime.now(UTC),
            assessment_id=ASSESSMENT_ID,
        ),
    )


def test_corrupt_files_are_ignored_and_invalid_paths_are_rejected(tmp_path: Path) -> None:
    directory = tmp_path / "records"
    directory.mkdir()
    (directory / "corrupt.json").write_text("not json", encoding="utf-8")
    store = LeadStore(directory)

    assert store.list_leads() == []
    _assert_raises(LeadStoreError, lambda: store.load_lead("../outside"))
