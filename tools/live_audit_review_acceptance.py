"""TRON real-public-site acceptance, isolated from Webify customer state.

This is an engineering evidence capture, not a real client engagement. The default
target is IANA's example.com; an operator can explicitly supply another public URL.
"""
from __future__ import annotations

import argparse
import json
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from veridra.core import normalize_url, resolve_public_ips
from veridra.exports import build_evidence_package
from veridra.reports import render_report
from veridra.service import assess_url


def _public_target(value: str) -> str:
    target = normalize_url(value)
    hostname = urlparse(target).hostname
    if hostname is None:
        raise ValueError("Missing public hostname")
    resolve_public_ips(hostname)
    return target


def _review_summary(assessment: object) -> dict[str, object]:
    result = assessment.model_dump(mode="json")
    findings = result["findings"]
    pages = result.get("pages", [])
    observed_bytes = sum(int(p.get("response_bytes", 0)) for p in pages)
    limited_evidence = len(pages) <= 1 and observed_bytes < 2000
    demonstration_site = (urlparse(str(result["target"])).hostname or "").lower() in {"example.com", "www.example.com"}
    return {
        "contract": "veridra_live_audit_review_v1",
        "commercial_quality_accepted": False,
        "pages_observed": len(pages),
        "observed_html_bytes": observed_bytes,
        "limited_content_evidence": limited_evidence,
        "evidence_quality_warning": (
            "Only one very small HTML page was observed. Many absent features may "
            "reflect a placeholder or incomplete website; verify the intended scope "
            "before classifying them as actionable commercial defects."
            if limited_evidence else None
        ),
        "review_status": "manual_applicability_review_required",
        "demonstration_site": demonstration_site,
        "applicability_warning": (
            "Example.com is not a representative local business. Missing local-business "
            "signals cannot be treated as business defects without confirming site purpose."
            if demonstration_site else
            "Confirm the site business model before treating absent local-business "
            "features as genuine remediation opportunities."
        ),
        "mode": result["mode"],
        "target": result["target"],
        "generated_at": result["generated_at"],
        "elapsed_ms": result["elapsed_ms"],
        "summary": result["summary"],
        "area_summary": result["area_summary"],
        "attention_findings": [
            {
                "id": item["id"],
                "area": item["area"],
                "severity": item["severity"],
                "title": item["title"],
                "summary": item["summary"],
                "recommendation": item["recommendation"],
            }
            for item in findings if item["status"] == "attention"
        ],
        "review_questions": [
            "Are observations grounded in publicly verifiable evidence?",
            "Are any findings misleading, exaggerated or false positives?",
            "Would the report help explain a useful, actionable Webify service?",
            "Are limitations and unavailable results clearly explained?",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="https://example.com/")
    parser.add_argument("--output", type=Path, default=Path.home() / "Downloads")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    archive_path = args.output / f"VERIDRA_LIVE_AUDIT_REVIEW_{stamp}.zip"
    with tempfile.TemporaryDirectory(prefix="veridra-live-review-") as dirname:
        work = Path(dirname)
        status: dict[str, object] = {"contract": "veridra_live_audit_review_v1", "passed": False}
        try:
            target = _public_target(args.url)
            print(f"[LIVE AUDIT] Running bounded public assessment: {target}", flush=True)
            # Do not set tenant DB paths or write to the operator's actual data.
            assessment = assess_url(target)
            if assessment.mode != "live" or assessment.summary["total"] == 0:
                raise RuntimeError("Live assessment returned no verifiable findings")
            evidence = build_evidence_package(assessment)
            (work / "evidence.zip").write_bytes(evidence.content)
            (work / "report.html").write_text(render_report(assessment), encoding="utf-8")
            summary = _review_summary(assessment)
            status.update({
                "passed": True,
                "target": target,
                "summary": assessment.summary,
                "elapsed_ms": assessment.elapsed_ms,
                "output": archive_path.name,
                "report_pdf": "unavailable",
                "commercial_quality_accepted": False,
                "quality_review_required": True,
            })
            (work / "review.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
            # A review verdict is evidence-gated; a successful audit is not
            # automatic acceptance of business impact or accessibility claims.
            verdict = {
                "technical_execution": "passed",
                "commercial_acceptance": "pending_operator_review",
                "limited_content_evidence": summary["limited_content_evidence"],
                "accessibility_verification": "not_confirmed_by_static_scan",
                "report_review": "pending_operator_review",
                "manual_checks": summary["review_questions"],
            }
            (work / "quality-verdict.json").write_text(
                json.dumps(verdict, indent=2), encoding="utf-8"
            )
            try:
                from playwright.sync_api import sync_playwright
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(headless=True)
                    try:
                        page = browser.new_page(viewport={"width": 1365, "height": 900})
                        page.goto((work / "report.html").as_uri(), wait_until="load")
                        page.pdf(path=str(work / "report.pdf"), format="A4", print_background=True)
                        page.screenshot(path=str(work / "report-preview.png"), full_page=True)
                        status["report_pdf"] = "created"
                        # Use the live browser for bounded accessibility triage.
                        # No form submission or private data collection.
                        browser_checks = []
                        candidates = [
                            p["url"] for p in assessment.model_dump(mode="json").get("pages", [])
                            if p.get("url", "").startswith("https://")
                        ][:3]
                        for site_url in candidates:
                            checked = {"url": site_url, "status": "unverified"}
                            try:
                                live = browser.new_page()
                                try:
                                    live.goto(site_url, wait_until="domcontentloaded", timeout=15000)
                                    checked["evidence"] = live.evaluate("""() => {
                                        const controls = [...document.querySelectorAll('input:not([type=hidden]),select,textarea')];
                                        const interactives = [...document.querySelectorAll('a,button')];
                                        const named = el => Boolean(
                                          el.getAttribute('aria-label')?.trim() ||
                                          el.getAttribute('aria-labelledby')?.trim() ||
                                          el.getAttribute('title')?.trim() ||
                                          el.labels?.length ||
                                          el.innerText?.trim() ||
                                          el.querySelector('img[alt]')?.getAttribute('alt')?.trim()
                                        );
                                        return {
                                          controls_count: controls.length,
                                          unnamed_controls_count: controls.filter(el => !named(el)).length,
                                          interactive_count: interactives.length,
                                          unnamed_interactive_count: interactives.filter(el => !named(el)).length,
                                          limitation: 'DOM heuristic; not full WCAG accessibility testing'
                                        };
                                    }""")
                                    checked["status"] = "dom_heuristic_collected"
                                finally:
                                    live.close()
                            except Exception as exc:
                                checked["reason"] = type(exc).__name__
                            browser_checks.append(checked)
                        (work / "browser-accessibility-triage.json").write_text(
                            json.dumps(browser_checks, indent=2), encoding="utf-8"
                        )
                    finally:
                        browser.close()
            except Exception as exc:
                status["pdf_warning"] = type(exc).__name__
        except Exception as exc:
            status["error_type"] = type(exc).__name__
            status["error"] = str(exc)[:400]
        (work / "status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(work.iterdir()):
                archive.write(path, arcname=path.name)
    print(json.dumps(status, indent=2), flush=True)
    print(f"Evidence ZIP: {archive_path}", flush=True)
    return 0 if status["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
