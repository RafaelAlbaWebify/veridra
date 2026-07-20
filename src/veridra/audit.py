from __future__ import annotations

import json
from pathlib import Path

from .app import dashboard
from .core import demo_assessment
from .reports import render_report


def run_audit(root: Path, output: Path) -> dict[str, object]:
    output.mkdir(parents=True, exist_ok=True)
    demo = demo_assessment()
    dashboard_html = dashboard(demo, demo_mode=True)
    report_html = render_report(demo)
    checks = {
        "required_files": all(
            (root / path).exists()
            for path in [
                "pyproject.toml",
                "README.md",
                "src/veridra/app.py",
                "src/veridra/reports.py",
                "tests",
            ]
        ),
        "responsive_ui": "meta name='viewport'" in dashboard_html,
        "scope_notice": "not a penetration test" in dashboard_html,
        "assessment_form": "name='url'" in dashboard_html,
        "printable_report": "window.print()" in report_html,
        "report_scope_notice": "not a penetration test" in report_html,
        "demo_evidence": demo.summary["total"] > 0,
    }
    report: dict[str, object] = {
        "passed": all(checks.values()),
        "checks": checks,
    }
    (output / "audit-report.json").write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )
    return report


def main() -> None:
    report = run_audit(Path.cwd(), Path("artifacts/audit"))
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["passed"] else 1)
