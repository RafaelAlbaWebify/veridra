"""Read-only, offline WordPress Care lab evidence index. No DB writes or secrets."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from datetime import datetime, timezone

CONTRACTS = {
    "webify_wordpress_care_lab_v1": ("checks", "passed"),
    "wordpress_care_isolated_restore_v1": ("checks", "passed"),
    "webify_wordpress_care_cycle_v1": ("steps", "passed"),
}
ALLOWED_DIRS = ("care-maintenance", "care-restore", "care-cycle")

def collect(lab: Path) -> dict:
    base = lab / "acceptance"
    items = []
    for folder in ALLOWED_DIRS:
        path = base / folder
        if not path.is_dir():
            continue
        for file in sorted(path.glob("*.json")):
            try:
                if file.is_symlink() or file.stat().st_size > 1048576:
                    raise ValueError("Symlink or oversized evidence")
                obj = json.loads(file.read_text(encoding="utf-8-sig"))
                if not isinstance(obj, dict):
                    raise ValueError("Evidence is not an object")
                contract = obj.get("contract")
                if contract not in CONTRACTS:
                    raise ValueError("Unsupported contract")
                if type(obj.get("passed")) is not bool:
                    raise ValueError("Missing boolean passed")
                section = CONTRACTS[contract][0]
                if not isinstance(obj.get(section), dict):
                    raise ValueError("Missing checks/steps")
                states = list(obj[section].values())
                if not states or not all(s in ("PASS", "NOT_RUN", "FAIL") for s in states):
                    raise ValueError("Invalid test states")
                valid = bool(obj["passed"]) and all(s == "PASS" for s in states)
                items.append({"file": str(file.relative_to(base)), "contract": contract, "status": "PASS" if valid else "FAIL"})
            except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
                items.append({"file": str(file.relative_to(base)), "contract": None, "status": "INVALID", "reason": str(exc)})
    counts = {state: sum(i["status"] == state for i in items) for state in ("PASS", "FAIL", "INVALID")}
    return {"contract": "webify_wordpress_care_evidence_index_v1", "generated_utc": datetime.now(timezone.utc).isoformat(), "lab": str(lab), "counts": counts, "items": items}

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lab", type=Path, default=Path.home() / "Documents" / "WebifyLabs" / "wordpress-care")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = collect(args.lab)
    print(json.dumps(report, indent=2, ensure_ascii=False) if args.json else f"WordPress Care evidence: {report['counts']}")
    return 1 if report["counts"]["FAIL"] or report["counts"]["INVALID"] or not report["items"] else 0

if __name__ == "__main__":
    raise SystemExit(main())
