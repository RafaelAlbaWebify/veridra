#!/usr/bin/env python3
"""Build compact AI context bundles from a local Git checkout."""

from pathlib import Path
from datetime import datetime, timezone
import argparse
import json
import subprocess

CANONICAL = [
    ".ai/CONTEXT.md",
    ".ai/PROJECT_STATE.json",
    ".ai/KNOWN_ISSUES.md",
    ".ai/OPERABILITY.md",
    ".ai/ROADMAP.md",
    ".ai/ARCHITECTURE.md",
    ".ai/DECISIONS.md",
    ".ai/REJECTED_APPROACHES.md",
    ".ai/TEST_STATUS.json",
    ".ai/FILE_MAP.md",
    ".ai/SESSION_PROTOCOL.md",
    "PROJECT_MEMORY.md",
    "README.md",
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


def git(root, *args):
    try:
        p = subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=15,
        )
        return p.stdout.strip() if p.returncode == 0 else ""
    except Exception:
        return ""


def repo_root(start):
    found = git(start, "rev-parse", "--show-toplevel")
    return Path(found).resolve() if found else Path(start).resolve()


def load_config(root):
    cfg = {"max_file_chars": 40000, "max_bundle_chars": 300000, "recent_commits": 8}
    path = root / ".ai" / "CONTEXT_BUNDLE.json"
    if path.exists():
        cfg.update(json.loads(path.read_text(encoding="utf-8")))
    return cfg


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
    return sorted(x for x in names if x and eligible(x) and (root / x).is_file())


def read_file(root, path, limit):
    try:
        text = (root / path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "", False
    if len(text) > limit:
        return text[:limit] + f"\n\n[TRUNCATED at {limit} chars]\n", True
    return text, False


def repository_map(files):
    return "\n".join(files)


def build(root, mode):
    cfg = load_config(root)
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

    parts = [
        "# AI Context Bundle\n",
        f"Generated: {datetime.now(timezone.utc).isoformat()}\n\nMode: **{mode}**\n",
        "## Usage contract\n\nThis is a transport snapshot, not durable project memory. Prefer verified runtime/test evidence, then current source/configuration, then canonical `.ai/` state. Record disagreements rather than silently reconciling them.\n",
        f"## Git state\n\nBranch: {branch}\n\nCommit: {commit}\n\nWorking tree:\n```text\n{status}\n```\n\nRecent commits:\n```text\n{recent}\n```\n",
        f"## Repository map\n\n```text\n{repository_map(files)}\n```\n",
    ]

    manifest = {"mode": mode, "branch": branch, "commit": commit, "files": [], "skipped": []}
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

    if mode in {"delta", "full"}:
        for path in changed:
            if not add(path, "changed"):
                break

    if mode == "full":
        for path in files:
            if not add(path, "repository"):
                break

    parts.append(f"## Bundle summary\n\nIncluded files: {len(manifest['files'])}\n\nChanged eligible files: {len(changed)}\n\nSkipped by budget: {len(manifest['skipped'])}\n")
    bundle = "\n".join(parts)
    bundle_path.write_text(bundle, encoding="utf-8")
    manifest["generated_at"] = datetime.now(timezone.utc).isoformat()
    manifest["chars"] = len(bundle)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return bundle_path, manifest_path


def main():
    parser = argparse.ArgumentParser(description="Build layered AI repository context")
    parser.add_argument("--mode", choices=["bootstrap", "delta", "full"], default="bootstrap")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    root = repo_root(args.root)
    bundle, manifest = build(root, args.mode)
    print(f"AI context bundle: {bundle}")
    print(f"Manifest: {manifest}")


if __name__ == "__main__":
    main()
