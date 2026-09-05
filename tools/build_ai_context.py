from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AI = ROOT / ".ai"
OUT = AI / "AUTO_CONTEXT.md"


def git(*args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", *args],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def load_json(name: str) -> dict[str, object]:
    return json.loads((AI / name).read_text(encoding="utf-8"))


def main() -> int:
    state = load_json("PROJECT_STATE.json")
    tests = load_json("TEST_STATUS.json")
    branch = git("branch", "--show-current")
    commit = git("rev-parse", "HEAD")
    status = git("status", "--short") or "clean"
    recent = git("log", "-5", "--pretty=format:%h %ad %s", "--date=short")
    blockers = state.get("current_blockers", [])
    actions = state.get("next_recommended_actions", [])
    lines = [
        "# Auto-generated AI Context",
        "",
        f"Generated: {datetime.now(UTC).isoformat()}",
        f"Project: {state.get('project_name')}",
        f"Branch: {branch}",
        f"Commit: {commit}",
        f"Git status: {status}",
        f"Phase: {state.get('current_phase')}",
        f"Milestone: {state.get('current_milestone')}",
        f"Operability: {state.get('operability_percentage')}%",
        f"Latest tested commit: {tests.get('latest_tested_commit')}",
        f"Latest test result: {tests.get('overall_result')}",
        "",
        "## Current blockers",
        *[f"- {item}" for item in blockers],
        "",
        "## Next actions",
        *[f"- {item}" for item in actions],
        "",
        "## Recent commits",
        "```",
        recent,
        "```",
        "",
        (
            "Manual/history files such as DECISIONS.md and REJECTED_APPROACHES.md "
            "are never overwritten by this tool."
        ),
    ]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(OUT.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
