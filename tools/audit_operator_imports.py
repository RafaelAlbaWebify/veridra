"""Static integrity gate for Webify's operator-only Python source tree.

Run: python tools/audit_operator_imports.py
Exit status is nonzero for missing local package imports or retired SaaS imports.
No external dependencies, configuration, internet access or client data are needed.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "veridra"
RETIRED = frozenset(
    {
        "plans_web", "signup_web", "stripe_billing", "stripe_billing_web",
        "stripe_webhook_verification", "subscription_authority",
        "subscription_authority_cli", "tenant_signup", "tenant_team_web",
        "workspace_members_web", "workspace_web", "runtime_billing",
        "signup_legal_evidence", "local_provider_snapshot",
        "local_provider_reconcile", "local_h6_acceptance",
        "local_h6_phase4", "local_h6_phase5", "local_h6_phase6",
        "deployment_acceptance", "deployment_acceptance_cli",
        "hosted_provider_preflight", "workspace_enforcement",
    }
)


def missing_local_imports(directory: Path) -> list[str]:
    modules = {p.stem for p in directory.glob("*.py")}
    issues: list[str] = []
    for path in sorted(directory.glob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, UnicodeError) as exc:
            issues.append(f"{path.name}: cannot parse: {exc}")
            continue
        for node in ast.walk(tree):
            names: set[str] = set()
            if isinstance(node, ast.ImportFrom):
                if node.level == 1:
                    if node.module:
                        names.add(node.module.split(".", 1)[0])
                    else:
                        names.update(alias.name.split(".", 1)[0] for alias in node.names)
                elif node.level == 0 and node.module and node.module.startswith("veridra."):
                    names.add(node.module.split(".")[1])
            elif isinstance(node, ast.Import):
                names.update(
                    alias.name.split(".")[1]
                    for alias in node.names
                    if alias.name.startswith("veridra.") and "." in alias.name
                )
            for name in sorted(names):
                if name in RETIRED:
                    issues.append(f"{path.name}:{node.lineno}: retired import {name}")
                elif name not in modules and not (directory / name / "__init__.py").is_file():
                    # 'from . import symbol' may refer to a package attribute, so only
                    # report missing files for explicit modules under veridra.
                    if not (isinstance(node, ast.ImportFrom) and node.module is None):
                        issues.append(f"{path.name}:{node.lineno}: missing local module {name}")
    return issues


# Executable entry points may refer to deleted Python modules as strings.
# Restrict this pass to launcher/CI entry points, not historical documentation.
LAUNCHER_PATHS = (
    ROOT / "scripts" / "windows",
    ROOT / "tools",
)
RETIRED_SCRIPT_MODULES = frozenset(
    {"local_provider_snapshot", "local_provider_reconcile",
     "local_h6_acceptance", "local_h6_phase4", "local_h6_phase5",
     "local_h6_phase6", "subscription_authority_cli",
     "deployment_acceptance_cli", "hosted_provider_preflight"}
)


def retired_launcher_references(root: Path) -> list[str]:
    issues: list[str] = []
    files = list((root / "scripts" / "windows").glob("*.ps1"))
    files.extend((root / "tools").glob("*.py"))
    files.extend(root.glob("*.bat"))
    for path in sorted(files):
        if path.name == "audit_operator_imports.py":
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            issues.append(f"{path.relative_to(root)}: cannot read: {exc}")
            continue
        for number, line in enumerate(content.splitlines(), 1):
            for module in RETIRED_SCRIPT_MODULES:
                if f"veridra.{module}" in line:
                    issues.append(
                        f"{path.relative_to(root)}:{number}: retired launcher module {module}"
                    )
    return issues


def main() -> int:
    issues = missing_local_imports(PACKAGE) + retired_launcher_references(ROOT)
    if issues:
        for issue in issues:
            print("FAIL", issue)
        print(f"FAILED: {len(issues)} Python import/reference issue(s)")
        return 1
    print(f"PASS: {len(list(PACKAGE.glob('*.py')))} Python modules parsed; "
          "no missing direct local modules or retired SaaS imports")
    return 0


if __name__ == "__main__":
    sys.exit(main())
