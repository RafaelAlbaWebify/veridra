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
    return {
        "changed_files": normalized,
        "source_consumers": affected,
        "candidate_tests": impacted_tests,
        "unmodelled_changed_files": unmodelled,
        "dynamic_import_files": sorted(dynamic),
        "parse_errors": parse_errors,
        "coverage_note": (
            "Static Python imports only; runtime route registration, filesystem contracts, "
            "shell scripts and indirect tests require manual review."
        ),
        "requires_full_gate": bool(unmodelled or parse_errors or (owners and not impacted_tests)),
    }


def changed(base: str, root: Path = ROOT) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMRT", f"{base}...HEAD"],
        cwd=root, text=True, capture_output=True, check=True,
    )
    return [p for p in result.stdout.splitlines() if p]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", help="repo-relative changed paths")
    parser.add_argument("--base", help="Git base ref for three-dot diff")
    parser.add_argument(
        "--strict", action="store_true", help="fail when changed modules fail to parse"
    )
    args = parser.parse_args()
    paths = sorted(set([*args.files, *(changed(args.base) if args.base else [])]))
    if not paths:
        parser.error("specify file paths and/or --base")
    report = analyze(paths)
    print(json.dumps(report, indent=2))
    return int(args.strict and bool(report["parse_errors"]))


if __name__ == "__main__":
    raise SystemExit(main())
