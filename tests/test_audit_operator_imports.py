from __future__ import annotations

from pathlib import Path

from tools.audit_operator_imports import missing_local_imports


def test_audit_accepts_valid_relative_and_absolute_imports(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text(
        "from .b import item\nimport veridra.b\nfrom . import b\n",
        encoding="utf-8",
    )
    (tmp_path / "b.py").write_text("item = 1\n", encoding="utf-8")
    assert missing_local_imports(tmp_path) == []


def test_audit_catches_missing_imports_and_retired_saas(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text(
        "from .unknown import value\nfrom .stripe_billing import StripeBillingConfig\n",
        encoding="utf-8",
    )
    issues = missing_local_imports(tmp_path)
    assert any("missing local module unknown" in issue for issue in issues)
    assert any("retired import stripe_billing" in issue for issue in issues)


def test_audit_reports_syntax_errors(tmp_path: Path) -> None:
    (tmp_path / "invalid.py").write_text("def incomplete(:\n", encoding="utf-8")
    assert any("cannot parse" in issue for issue in missing_local_imports(tmp_path))
