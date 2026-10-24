"""Conservative, dependency-aware change impact report for VERIDRA.

Uses only Python stdlib, works offline, reports uncertainty instead of inventing coverage.
Pass explicit paths or use --base to compare with a Git ref. It does not mutate the checkout.
"""
from __future__ import annotations

import argparse
import ast
import json
import subprocess
from collections import defaultdict, deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "veridra"
TESTS = ROOT / "tests"


def modules(root: Path = ROOT) -> dict[str, Path]:
    paths = [*(root / "src" / "veridra").rglob("*.py"), *(root / "tests").rglob("*.py")]
    result = {}
    for path in paths:
        rel = path.relative_to(root)
        if rel.parts[0] == "src":
            module = ".".join(rel.with_suffix("").parts[1:])
            if module.endswith(".__init__"):
                module = module[: -len(".__init__")]
        else:
            module = ".".join(rel.with_suffix("").parts)
        result[module] = path
    return result


def imports(module: str, path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    edges = set()
    package = module.split(".")[:-1]
    if path.name == "__init__.py":
        package = module.split(".")
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            edges.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            prefix = package[: max(0, len(package) - node.level + 1)] if node.level else []
            base = ".".join([*prefix, *(node.module.split(".") if node.module else [])])
            if base:
                edges.add(base)
            edges.update(base + "." + alias.name for alias in node.names if base)
    return edges



# High-risk boundaries are deliberately explicit: these are not inferable from imports alone.
# Each rule is a conservative escalation, not evidence that every consumer has been found.
BOUNDARIES = {
    "web-routes": {
        "names": ("app.py", "runtime.py", "runtime_route_policy.py"),
        "suffixes": ("_web.py",),
        "tests": ("test_session_lifecycle_api.py", "test_agency_proposal_transition_web.py"),
    },
    "tenant-persistence": {
        "names": ("identity_tenancy.py",),
        "suffixes": ("_store.py", "_migration.py"),
        "tests": ("test_backup_restore.py", "test_project_store.py"),
    },
    "background-jobs": {
        "names": ("crawl_worker.py", "monitoring_worker.py"),
        "suffixes": ("_worker_service.py", "_jobs.py"),
        "tests": ("test_monitoring_jobs_api_worker.py", "test_monitoring_service.py"),
    },
    "billing-authority": {
        "names": ("subscription_authority.py", "runtime_billing.py"),
        "suffixes": ("_stripe.py",),
        "tests": ("test_subscription_authority.py",),
    },
}


def boundary_risks(changed_paths: list[str], root: Path) -> list[dict[str, object]]:
    """Flag cross-boundary review; candidate tests are not a coverage guarantee."""
    risks: list[dict[str, object]] = []
    for label, rule in BOUNDARIES.items():
        matching = [
            path for path in changed_paths
            if path.startswith("src/veridra/") and (
                Path(path).name in rule["names"]
                or Path(path).name.endswith(rule["suffixes"])
            )
        ]
        if matching:
            risks.append({
                "boundary": label,
                "changed": matching,
                "suggested_tests": [
                    "tests/" + name for name in rule["tests"]
                    if (root / "tests" / name).is_file()
                ],
                "manual_review": True,
            })
    return risks


def registered_routes(root: Path = ROOT) -> list[dict[str, str]]:
    """Derive router sources from literal app.include_router calls, marking guards."""
    registrations: list[dict[str, str]] = []
    for entry in ("src/veridra/app.py", "src/veridra/runtime.py"):
        path = root / entry
        if not path.is_file():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        aliases: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                for alias in node.names:
                    if alias.name == "router":
                        aliases[alias.asname or "router"] = (
                            "src/veridra/" + node.module.rsplit(".", 1)[-1] + ".py"
                        )
        def inspect(
            stmts: list[ast.stmt], conditional: bool = False,
            *, entry: str = entry, aliases: dict[str, str] = aliases,
        ) -> None:
            for stmt in stmts:
                if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
                    call = stmt.value
                    if (
                        isinstance(call.func, ast.Attribute)
                        and call.func.attr == "include_router"
                        and call.args and isinstance(call.args[0], ast.Name)
                    ):
                        symbol = call.args[0].id
                        registrations.append({
                            "entrypoint": entry,
                            "symbol": symbol,
                            "source": aliases.get(symbol, "unresolved"),
                            "conditional": str(conditional).lower(),
                        })
                elif isinstance(stmt, ast.If):
                    inspect(stmt.body, True)
                    inspect(stmt.orelse, True)
        inspect(tree.body)
    return registrations


def analyze(paths: list[str], root: Path = ROOT) -> dict[str, object]:
    known = modules(root)
    normalized = sorted(set(p.replace("\\", "/").removeprefix("./") for p in paths))
    owners = {
        name for name, path in known.items()
        if path.relative_to(root).as_posix() in normalized
    }
    reverse: dict[str, set[str]] = defaultdict(set)
    parse_errors = []
    dynamic = []
    for name, path in known.items():
        try:
            for dependency in imports(name, path):
                candidates = [dependency]
                while "." in candidates[-1]:
                    candidates.append(candidates[-1].rsplit(".", 1)[0])
                for candidate in candidates:
                    if candidate in known and candidate != name:
                        reverse[candidate].add(name)
        except (OSError, SyntaxError, UnicodeError) as exc:
            parse_errors.append({"path": str(path.relative_to(root)), "error": str(exc)})
        source = path.read_text(encoding="utf-8", errors="replace")
        if "importlib.import_module(" in source or "__import__(" in source:
            dynamic.append(path.relative_to(root).as_posix())
    reached = set(owners)
    queue = deque(owners)
    while queue:
        for consumer in reverse[queue.popleft()]:
            if consumer not in reached:
                reached.add(consumer)
                queue.append(consumer)
    impacted_tests = sorted(
        str(known[name].relative_to(root)) for name in reached if name.startswith("tests.")
    )
    affected = sorted(
        str(known[name].relative_to(root)) for name in reached if name.startswith("veridra.")
    )
    known_files = {v.relative_to(root).as_posix() for v in known.values()}
    unmodelled = [p for p in normalized if p not in known_files]
    dynamic_impacted = sorted(
        str(known[name].relative_to(root)) for name in reached
        if known[name].relative_to(root).as_posix() in dynamic
    )
    boundaries = boundary_risks(normalized, root)
    impacted_routes = [
        item for item in registered_routes(root) if item["source"] in normalized
    ]
    return {
        "changed_files": normalized,
        "source_consumers": affected,
        "candidate_tests": impacted_tests,
        "unmodelled_changed_files": unmodelled,
        "dynamic_import_files": sorted(dynamic),
        "impacted_dynamic_import_files": dynamic_impacted,
        "parse_errors": parse_errors,
        "critical_boundaries": boundaries,
        "registered_router_impacts": impacted_routes,
        "coverage_note": (
            "Static Python imports only; runtime route registration, filesystem contracts, "
            "shell scripts and indirect tests require manual review."
        ),
        "requires_full_gate": bool(
            unmodelled or parse_errors or dynamic_impacted or boundaries
            or impacted_routes or (owners and not impacted_tests)
        ),
    }


def changed(base: str, root: Path = ROOT) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMRTD", f"{base}...HEAD"],
        cwd=root, text=True, capture_output=True, check=True,
    )
    return [p for p in result.stdout.splitlines() if p]


def working_tree_changes(root: Path = ROOT) -> list[str]:
    """Include tracked edits and untracked files without modifying local state."""
    result = subprocess.run(
        ["git", "status", "--porcelain=v1", "-uall"],
        cwd=root, text=True, capture_output=True, check=True,
    )
    paths = []
    for line in result.stdout.splitlines():
        if len(line) < 4:
            continue
        value = line[3:]
        if " -> " in value:
            value = value.split(" -> ", 1)[1]
        paths.append(value.strip('"'))
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", help="repo-relative changed paths")
    parser.add_argument("--base", help="Git base ref for three-dot diff")
    parser.add_argument(
        "--working-tree", action="store_true",
        help="include local edits and untracked files",
    )
    parser.add_argument(
        "--strict", action="store_true", help="fail when changed modules fail to parse"
    )
    args = parser.parse_args()
    paths = sorted(set([
        *args.files, *(changed(args.base) if args.base else []),
        *(working_tree_changes() if args.working_tree else []),
    ]))
    if not paths and not (args.base or args.working_tree):
        parser.error("specify file paths, --base or --working-tree")
    report = analyze(paths)
    print(json.dumps(report, indent=2))
    return int(args.strict and bool(report["parse_errors"]))


if __name__ == "__main__":
    raise SystemExit(main())
