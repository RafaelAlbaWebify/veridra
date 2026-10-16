"""One-command Webify operator rehearsal using existing isolated acceptance suites.

The live audit checks a public site. The commercial lifecycle uses synthetic
prospects/payments and isolated state; these are separate evidence tracks.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path

EVIDENCE_PREFIXES = {
    "public_audit": "VERIDRA_LIVE_AUDIT_REVIEW_",
    "synthetic_lifecycle": "VERIDRA_OPERATOR_E2E_ACCEPTANCE_",
}


def _latest_after(folder: Path, prefix: str, started_ns: int) -> Path | None:
    choices = [
        path for path in folder.glob(prefix + "*.zip")
        if path.is_file() and path.stat().st_mtime_ns >= started_ns
    ]
    return max(choices, key=lambda p: p.stat().st_mtime_ns) if choices else None


def _run(repo: Path, command: list[str], output: Path) -> int:
    with output.open("w", encoding="utf-8") as handle:
        process = subprocess.Popen(
            command, cwd=repo, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, errors="replace",
        )
        assert process.stdout is not None
        for line in process.stdout:
            # Keep the operator informed without saving potentially sensitive
            # launcher output into the uploaded review bundle.
            print(line, end="", flush=True)
            handle.write(line)
        return process.wait()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="https://basecamp.com/")
    parser.add_argument("--output", type=Path, default=Path.home() / "Downloads")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    args.output.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    combined = args.output / f"VERIDRA_WEBIFY_ENGAGEMENT_REVIEW_{stamp}.zip"
    stages = [
        ("public_audit", ["cmd.exe", "/c", str(repo / "VERIDRA_LIVE_AUDIT_REVIEW.bat"),
                          "--url", args.url]),
        ("synthetic_lifecycle", ["cmd.exe", "/c",
                                 str(repo / "VERIDRA_OPERATOR_E2E_ACCEPTANCE.bat")]),
    ]
    results: dict[str, object] = {
        "contract": "veridra_webify_engagement_review_v1",
        "started_at": datetime.now(UTC).isoformat(),
        "public_target": args.url,
        "data_isolation": "live read-only audit; separate synthetic customer lifecycle",
        "outreach_sent": False,
        "real_payment_activated": False,
        "stages": {},
    }
    artifacts: dict[str, Path] = {}
    for stage, command in stages:
        started_ns = int(datetime.now(UTC).timestamp() * 1_000_000_000) - 2_000_000_000
        print(f"\n[ENGAGEMENT] {stage}: starting", flush=True)
        log = args.output / f"VERIDRA_{stage}_{stamp}.local.log"
        exit_code = _run(repo, command, log)
        # Logs stay on TRON and are NOT included in the review bundle.
        evidence = _latest_after(args.output, EVIDENCE_PREFIXES[stage], started_ns)
        state = "passed" if exit_code == 0 and evidence else "failed"
        results["stages"][stage] = {
            "status": state,
            "exit_code": exit_code,
            "evidence_present": evidence is not None,
        }
        if evidence:
            artifacts[stage] = evidence
        if state != "passed":
            print(f"[ENGAGEMENT] {stage}: FAILED; log kept locally at {log}", flush=True)
            break
    results["passed"] = len(artifacts) == len(stages) and all(
        item["status"] == "passed" for item in results["stages"].values()
    )
    results["commercial_quality_accepted"] = False
    results["operator_review_required"] = True
    results["finished_at"] = datetime.now(UTC).isoformat()
    with zipfile.ZipFile(combined, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("engagement-summary.json", json.dumps(results, indent=2))
        for stage, path in artifacts.items():
            archive.write(path, arcname=f"{stage}/{path.name}")
    print(json.dumps(results, indent=2), flush=True)
    print(f"Evidence ZIP: {combined}", flush=True)
    return 0 if results["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
