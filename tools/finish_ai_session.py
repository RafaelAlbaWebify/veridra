#!/usr/bin/env python3
"""Create a deterministic end-of-session handoff and refresh the delta context bundle."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from ai_context_bundle import build, changed_files, freshness, git, load_json, repo_root


def pick_list(data, *keys):
    for key in keys:
        value = data.get(key)
        if isinstance(value, list):
            return value
    return []


def main() -> int:
    root = repo_root(Path.cwd())
    out = root / ".ai" / "generated"
    out.mkdir(parents=True, exist_ok=True)

    commit = git(root, "rev-parse", "HEAD") or "unknown"
    branch = git(root, "branch", "--show-current") or "unknown"
    status = git(root, "status", "--short") or "clean"
    state = load_json(root / ".ai" / "PROJECT_STATE.json")
    fresh = freshness(root, commit)
    changed = changed_files(root)
    blockers = pick_list(state, "current_blockers", "blockers")
    next_actions = pick_list(state, "next_recommended_actions", "next_actions")
    now = datetime.now(UTC).isoformat()

    handoff = {
        "generated_at": now,
        "branch": branch,
        "commit": commit,
        "working_tree": status,
        "changed_files": changed,
        "freshness": fresh,
        "blockers": blockers,
        "next_actions": next_actions,
        "warning": (
            "Generated evidence only. Update canonical .ai files when "
            "project facts/decisions/status change."
        ),
    }
    handoff_json = json.dumps(handoff, indent=2, ensure_ascii=False) + "\n"
    (out / "SESSION_HANDOFF.json").write_text(handoff_json, encoding="utf-8")

    lines = [
        "# AI Session Handoff",
        "",
        f"Generated: {now}",
        f"Branch: `{branch}`",
        f"Commit: `{commit}`",
        "",
        f"Freshness: **{fresh['overall'].upper()}**",
        "",
        "## Working tree",
        "```text",
        status,
        "```",
        "",
        "## Changed files",
        *([f"- `{p}`" for p in changed] or ["- none"]),
        "",
        "## Current blockers",
        *([f"- {x}" for x in blockers] or ["- none recorded"]),
        "",
        "## Next actions",
        *([f"- {x}" for x in next_actions] or ["- none recorded"]),
        "",
        "## Canonical-state reminder",
        (
            "If project facts, decisions, issues, roadmap status or test evidence "
            "changed during the session, update the corresponding canonical `.ai/` "
            "file before treating this handoff as complete."
        ),
        "",
    ]
    (out / "SESSION_HANDOFF.md").write_text("\n".join(lines), encoding="utf-8")

    build(root, "delta")
    print(out / "SESSION_HANDOFF.md")
    print(out / "AI_CONTEXT_BUNDLE.md")
    print(f"Freshness: {fresh['overall']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
