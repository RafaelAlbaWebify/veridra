#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

from ai_context_bundle import build, load_modules, repo_root
from finish_ai_session import main as finish_session


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--module", required=True)
    args = parser.parse_args()
    root = repo_root(Path.cwd())
    modules = load_modules(root)
    assert args.module in modules, f"Unknown test module: {args.module}"

    for mode in ("bootstrap", "delta", "full"):
        bundle, manifest = build(root, mode)
        assert bundle.exists() and bundle.stat().st_size > 500
        assert manifest.exists()

    build(root, "bootstrap", args.module)
    manifest_path = root / ".ai/generated/AI_CONTEXT_MANIFEST.json"
    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest_data["module"] == args.module
    assert manifest_data["freshness"]["overall"] in {"current", "stale", "unknown"}
    assert any(
        str(item.get("category", "")).startswith("module:")
        for item in manifest_data["files"]
    ), "Module scope matched no files"

    assert finish_session() == 0
    handoff = root / ".ai/generated/SESSION_HANDOFF.json"
    assert handoff.exists()
    handoff_data = json.loads(handoff.read_text(encoding="utf-8"))
    assert handoff_data.get("commit") not in {None, "", "unknown"}
    assert (root / ".ai/generated/SESSION_HANDOFF.md").exists()

    print("PASS: bootstrap, delta, full, module scope, freshness and session handoff")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
