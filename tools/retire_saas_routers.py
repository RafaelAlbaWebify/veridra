"""Remove independently retired SaaS modules from the Webify operator tree.

Run from the repository root. Dry-run is the default.
No client databases, tenant stores or Presence Care integration are deleted.
"""
from __future__ import annotations

import argparse
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "veridra"
# These routers are not imported by runtime.py in the Webify-only branch.
RETIRED_ROUTERS = (
    "plans_web",
    "signup_web",
    "stripe_billing_web",
    "tenant_team_web",
    "workspace_members_web",
    "workspace_web",
)


def consumers(name: str) -> list[str]:
    """Return production Python modules statically importing a retired router."""
    found: list[str] = []
    for source in PACKAGE.glob("*.py"):
        if source.stem == name:
            continue
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.level and node.module and node.module.split(".")[0] == name:
                    found.append(source.name)
                elif node.module == "veridra." + name:
                    found.append(source.name)
                elif node.level and node.module in {None, "veridra"} and any(
                    alias.name == name for alias in node.names
                ):
                    found.append(source.name)
            elif isinstance(node, ast.Import):
                if any(alias.name == "veridra." + name for alias in node.names):
                    found.append(source.name)
    return sorted(set(found))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="delete only the six verified routers")
    args = parser.parse_args()
    blocked = False
    for name in RETIRED_ROUTERS:
        path = PACKAGE / f"{name}.py"
        callers = consumers(name)
        if callers:
            blocked = True
            print(f"BLOCKED {path.relative_to(ROOT)}: {', '.join(callers)}")
            continue
        if not path.exists():
            print(f"ALREADY ABSENT {path.relative_to(ROOT)}")
            continue
        if args.apply:
            path.unlink()
            print(f"REMOVED {path.relative_to(ROOT)}")
        else:
            print(f"WOULD REMOVE {path.relative_to(ROOT)}")
    return 1 if blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
