#!/usr/bin/env python3
"""Build compact, freshness-aware AI context bundles from a local Git checkout."""

from pathlib import Path
from datetime import datetime, timezone
import argparse
import fnmatch
import json
import re
import subprocess

CANONICAL = [
    ".ai/CONTEXT.md", ".ai/PROJECT_STATE.json", ".ai/KNOWN_ISSUES.md",
    ".ai/OPERABILITY.md", ".ai/ROADMAP.md", ".ai/ARCHITECTURE.md",
    ".ai/DECISIONS.md", ".ai/REJECTED_APPROACHES.md", ".ai/TEST_STATUS.json",
    ".ai/FILE_MAP.md", ".ai/SESSION_PROTOCOL.md", "PROJECT_MEMORY.md", "README.md",
]
TEXT_EXTENSIONS = {
    ".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".py", ".js", ".jsx", ".ts", ".tsx", ".html", ".css", ".sql",
    ".ps1", ".bat", ".cmd", ".sh",
}
SKIP_PARTS = {
    ".git", ".venv", "venv", "node_modules", "dist", "build", "coverage",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", "__pycache__", ".next",
}
COMMIT_RE = re.compile(r"^[0-9a-fA-F]{7,40}$")


def git(root, *args):
    try:
        p = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=20)
        return p.stdout.strip() if p.returncode == 0 else ""
    except Exception:
        return ""


def repo_root(start):
    found = git(start, "rev-parse", "--show-toplevel")
    return Path(found).resolve() if found else Path(start).resolve()


def load_json(path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {} if default is None else default


def load_config(root):
    cfg = {"max_file_chars": 40000, "max_bundle_chars": 300000, "recent_commits": 8}
    path = root / ".ai" / "CONTEXT_BUNDLE.json"
    if path.exists():
        cfg.update(load_json(path))
    return cfg


def load_modules(root):
    return load_json(root / ".ai" / "CONTEXT_MODULES.json", {"modules": {}}).get("modules", {})


def eligible(path):
    p = Path(path)
    if any(part in SKIP_PARTS for part in p.parts):
        return False
    if any(part.startswith(".") and part != ".ai" for part in p.parts):
        return False
    if p.name in {"package-lock.json", "yarn.lock", "pnpm-lock.yaml"}:
        return False
    return p.suffix.lower() in TEXT_EXTENSIONS


def tracked_files(root):
    return sorted(x for x in git(root, "ls-files").splitlines() if x and eligible(x))


def changed_files(root):
    names = set(git(root, "diff", "--name-only").splitlines())
    names.update(git(root, "diff", "--cached", "--name-only").splitlines())
    names.update(git(root, "ls-files", "--others", "--exclude-standard").splitlines())
    return sorted(x for x in names if x and eligible(x) and (root / x).is_file())


def read_file(root, path, limit):
    try:
        text = (root / path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "", False
    if len(text) > limit:
        return text[:limit] + f"\n\n[TRUNCATED at {limit} chars]\n", True
    return text, False


def commit_candidates(value, key=""):
    found = []
    if isinstance(value, dict):
        for k, v in value.items():
            found.extend(commit_candidates(v, str(k)))
    elif isinstance(value, list):
        for v in value:
            found.extend(commit_candidates(v, key))
    elif isinstance(value, str) and "commit" in key.lower() and COMMIT_RE.match(value.strip()):
        found.append(value.strip().lower())
    return found


def freshness(root, head):
    def check(name):
        path = root / ".ai" / name
        if not path.exists():
            return {"status": "missing", "commits": []}
        commits = list(dict.fromkeys(commit_candidates(load_json(path))))
        if not commits:
            return {"status": "unknown", "commits": []}
        matches = [c for c in commits if head.lower().startswith(c) or c.startswith(head.lower())]
        return {"status": "current" if matches else "stale", "commits": commits[:8]}

    state = check("PROJECT_STATE.json")
    tests = check("TEST_STATUS.json")
    handoff_path = root / ".ai" / "generated" / "SESSION_HANDOFF.json"
    handoff = {"status": "missing", "commit": None}
    if handoff_path.exists():
        data = load_json(handoff_path)
        c = str(data.get("commit", "")).lower()
        handoff = {"status": "current" if c and (head.lower().startswith(c) or c.startswith(head.lower())) else "stale",
                   "commit": c or None}
    statuses = [state["status"], tests["status"]]
    overall = "current" if statuses == ["current", "current"] else (
        "stale" if "stale" in statuses else "unknown")
    return {"overall": overall, "project_state": state, "tests": tests, "session_handoff": handoff}


def module_files(files, modules, module):
    if not module:
        return []
    spec = modules.get(module)
    if not spec:
        raise ValueError(f"Unknown module: {module}")
    patterns = spec.get("patterns", [])
    return [p for p in files if any(fnmatch.fnmatch(p, pat) for pat in patterns)]


def build(root, mode, module=None):
    cfg = load_config(root)
    modules = load_modules(root)
    outdir = root / ".ai" / "generated"
    outdir.mkdir(parents=True, exist_ok=True)
    bundle_path = outdir / "AI_CONTEXT_BUNDLE.md"
    manifest_path = outdir / "AI_CONTEXT_MANIFEST.json"

    files = tracked_files(root)
    changed = changed_files(root)
    branch = git(root, "branch", "--show-current") or "unknown"
    commit = git(root, "rev-parse", "HEAD") or "unknown"
    status = git(root, "status", "--short") or "clean"
    recent = git(root, "log", f"-{cfg['recent_commits']}", "--pretty=format:%h %ad %s", "--date=short")
    fresh = freshness(root, commit)
    scoped = module_files(files, modules, module)

    module_text = f"\nModule scope: **{module}** — {modules[module].get('description','')}\n" if module else ""
    parts = [
        "# AI Context Bundle\n",
        f"Generated: {datetime.now(timezone.utc).isoformat()}\n\nMode: **{mode}**\n{module_text}",
        "## Usage contract\n\nThis is a transport snapshot, not durable project memory. Prefer verified runtime/test evidence, then current source/configuration, then canonical `.ai/` state. Record disagreements rather than silently reconciling them.\n",
        f"## Freshness\n\nOverall: **{fresh['overall'].upper()}**\n\n```json\n{json.dumps(fresh, indent=2)}\n```\n",
        f"## Git state\n\nBranch: {branch}\n\nCommit: {commit}\n\nWorking tree:\n```text\n{status}\n```\n\nRecent commits:\n```text\n{recent}\n```\n",
        f"## Repository map\n\n```text\n{chr(10).join(files)}\n```\n",
    ]

    manifest = {"mode": mode, "module": module, "branch": branch, "commit": commit,
                "freshness": fresh, "files": [], "skipped": []}
    included = set()

    def add(path, category):
        if path in included or not (root / path).is_file():
            return True
        text, truncated = read_file(root, path, int(cfg["max_file_chars"]))
        if not text:
            return True
        if sum(len(x) for x in parts) + len(text) > int(cfg["max_bundle_chars"]):
            manifest["skipped"].append(path)
            return False
        parts.append(f"## {category}: {path}\n\nSource: `{path}`\n\n```\n{text}\n```\n")
        manifest["files"].append({"path": path, "category": category, "chars": len(text), "truncated": truncated})
        included.add(path)
        return True

    for path in CANONICAL:
        if (root / path).is_file():
            add(path, "canonical")
    handoff_rel = ".ai/generated/SESSION_HANDOFF.md"
    if (root / handoff_rel).exists():
        add(handoff_rel, "latest-session-handoff")

    for path in scoped:
        if not add(path, f"module:{module}"):
            break

    if mode in {"delta", "full"}:
        for path in changed:
            if not add(path, "changed"):
                break

    if mode == "full" and not module:
        for path in files:
            if not add(path, "repository"):
                break

    parts.append(f"## Bundle summary\n\nIncluded files: {len(manifest['files'])}\n\nChanged eligible files: {len(changed)}\n\nModule files matched: {len(scoped)}\n\nSkipped by budget: {len(manifest['skipped'])}\n")
    bundle = "\n".join(parts)
    bundle_path.write_text(bundle, encoding="utf-8")
    manifest["generated_at"] = datetime.now(timezone.utc).isoformat()
    manifest["chars"] = len(bundle)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return bundle_path, manifest_path


def main():
    parser = argparse.ArgumentParser(description="Build layered AI repository context")
    parser.add_argument("--mode", choices=["bootstrap", "delta", "full"], default="bootstrap")
    parser.add_argument("--module", default=None)
    parser.add_argument("--list-modules", action="store_true")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    root = repo_root(args.root)
    if args.list_modules:
        modules = load_modules(root)
        for key, spec in modules.items():
            print(f"{key}: {spec.get('description','')}")
        return
    try:
        bundle, manifest = build(root, args.mode, args.module)
    except ValueError as exc:
        raise SystemExit(str(exc))
    print(f"AI context bundle: {bundle}")
    print(f"Manifest: {manifest}")


if __name__ == "__main__":
    main()
