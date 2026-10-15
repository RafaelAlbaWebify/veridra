from __future__ import annotations

import runpy
from pathlib import Path

_audit = runpy.run_path(
    str(Path(__file__).resolve().parents[1] / "tools" / "audit_operator_imports.py")
)
missing_local_imports = _audit["missing_local_imports"]
retired_launcher_references = _audit["retired_launcher_references"]


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


def test_launcher_audit_detects_removed_provider_module(tmp_path: Path) -> None:
    scripts = tmp_path / "scripts" / "windows"
    scripts.mkdir(parents=True)
    script = scripts / "launcher.ps1"
    script.write_text(
        "python -m veridra.local_provider_snapshot --tenant-id abc\\n",
        encoding="utf-8",
    )
    issues = retired_launcher_references(tmp_path)
    assert len(issues) == 1
    assert "retired launcher module local_provider_snapshot" in issues[0]


def test_launcher_audit_ignores_unrelated_presence_care_script(
    tmp_path: Path,
) -> None:
    (tmp_path / "tools").mkdir()
    script = tmp_path / "tools" / "presence_care.py"
    script.write_text("print('Presence Care mirror')\\n", encoding="utf-8")
    assert retired_launcher_references(tmp_path) == []
