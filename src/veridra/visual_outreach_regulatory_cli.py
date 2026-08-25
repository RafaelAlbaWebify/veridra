from __future__ import annotations

import argparse
import html
import json
import tempfile
import zipfile
from collections.abc import Sequence
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import Page, sync_playwright

from .visual_outreach_evidence_strict_cli import _latest_audit_zip, _safe_routes
from .visual_outreach_evidence_strict_cli import run as strict_run

_DPC_PRIVACY_POLICY = "https://www.dataprotection.ie/en/faqs/responsibilities-data-controllers/how-do-i-make-privacy-policy"
_DPC_TRANSPARENCY = "https://www.dataprotection.ie/en/organisations/know-your-obligations/transparency"
_GDPR_ARTICLE_83 = "https://eur-lex.europa.eu/eli/reg/2016/679/oj"
_PRIVACY_TERMS = ("privacy", "data protection", "cookie policy", "privacy policy")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="veridra-visual-outreach-evidence")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--downloads", type=Path, default=Path.home() / "Downloads")
    parser.add_argument("--output-directory", type=Path, default=Path.home() / "Downloads")
    parser.add_argument("--max-businesses", type=int, default=15)
    parser.add_argument("--max-issues-per-business", type=int, default=3)
    parser.add_argument("--navigation-timeout-ms", type=int, default=20_000)
    parser.add_argument("--country-code", default="")
    return parser


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _integer(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _is_privacy_link(link_text: str, target_url: str) -> bool:
    folded = f"{link_text} {target_url}".casefold()
    return any(term in folded for term in _PRIVACY_TERMS)


def regulatory_relevance(
    *, country_code: str, link_text: str, target_url: str, status_code: int
) -> dict[str, object] | None:
    if country_code.strip().upper() != "IE" or status_code < 400:
        return None
    if not _is_privacy_link(link_text, target_url):
        return None
    return {
        "jurisdiction": "Ireland",
        "topic": "GDPR transparency / privacy information",
        "legal_basis": "GDPR Articles 12-14; Irish Data Protection Commission transparency guidance",
        "relevance": (
            "If this broken link means the required privacy information is not otherwise easily "
            "accessible, it may create a GDPR transparency compliance issue. The broken link alone "
            "does not prove an infringement."
        ),
        "legal_maximum_exposure": (
            "For infringements of data-subject rights under GDPR Articles 12-22, Article 83(5) "
            "provides for administrative fines up to EUR 20,000,000 or, for an undertaking, up to "
            "4% of total worldwide annual turnover of the preceding financial year, whichever is higher."
        ),
        "practical_risk": "Potential compliance relevance; actual enforcement depends on the full facts.",
        "estimated_actual_fine": "Not responsibly estimable from public website evidence alone.",
        "sources": [
            {"title": "Irish DPC: How do I make a privacy policy?", "url": _DPC_PRIVACY_POLICY},
            {"title": "Irish DPC: Transparency", "url": _DPC_TRANSPARENCY},
            {"title": "GDPR Article 83 - EUR-Lex", "url": _GDPR_ARTICLE_83},
        ],
    }


def _goto_and_capture(page: Page, url: str, path: Path, timeout_ms: int, status_code: int) -> bool:
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return False
        page.set_viewport_size({"width": 1280, "height": 900})
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        page.wait_for_timeout(800)
        page.evaluate(
            """
            status => {
              const badge=document.createElement('div');
              badge.textContent=`Destination returned HTTP ${status}`;
              badge.style.position='fixed';
              badge.style.left='24px';
              badge.style.top='24px';
              badge.style.zIndex='2147483647';
              badge.style.background='#d40000';
              badge.style.color='#fff';
              badge.style.font='700 18px Arial,sans-serif';
              badge.style.padding='10px 14px';
              badge.style.borderRadius='6px';
              document.body.appendChild(badge);
            }
            """,
            status_code,
        )
        page.screenshot(path=str(path), full_page=False)
        return True
    except Exception:
        return False


def _latest_visual_zip(output_directory: Path) -> Path:
    values = sorted(
        output_directory.glob("VERIDRA_VISUAL_EVIDENCE_STRICT_*.zip"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    if not values:
        raise FileNotFoundError("Strict visual evidence output was not created.")
    return values[0]


def _augment_rows(
    *, rows: list[dict[str, object]], root: Path, country_code: str, timeout_ms: int
) -> tuple[int, int]:
    destination_screenshots = 0
    regulatory_count = 0
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        _safe_routes(context)
        page = context.new_page()
        for row in rows:
            evidence = row.get("evidence")
            if not isinstance(evidence, list):
                continue
            for item in evidence:
                if not isinstance(item, dict) or item.get("issue_type") != "broken_link":
                    continue
                details = item.get("details")
                if not isinstance(details, dict):
                    continue
                target_url = _text(details.get("target_url"))
                link_text = _text(details.get("link_text"))
                status_code = _integer(details.get("status_code"))
                source_path = _text(item.get("screenshot_path"))
                if not target_url or status_code < 400 or not source_path:
                    continue
                source_file = Path(source_path)
                result_name = f"{source_file.stem}-result.png"
                result_rel = source_file.with_name(result_name)
                result_path = root / result_rel
                result_path.parent.mkdir(parents=True, exist_ok=True)
                if _goto_and_capture(page, target_url, result_path, timeout_ms, status_code):
                    item["destination_screenshot_path"] = result_rel.as_posix()
                    destination_screenshots += 1
                regulatory = regulatory_relevance(
                    country_code=country_code,
                    link_text=link_text,
                    target_url=target_url,
                    status_code=status_code,
                )
                if regulatory is not None:
                    item["regulatory_relevance"] = regulatory
                    regulatory_count += 1
        context.close()
        browser.close()
    return destination_screenshots, regulatory_count


def _summary(rows: list[dict[str, object]]) -> str:
    parts = [
        "<!doctype html><html><head><meta charset='utf-8'><title>VERIDRA visual evidence</title>",
        "<style>body{font-family:Arial,sans-serif;max-width:1100px;margin:40px auto;padding:0 20px;color:#202124}img{max-width:100%;border:1px solid #ccc;border-radius:8px;margin:8px 0}.prospect{margin:38px 0;padding-top:22px;border-top:1px solid #ddd}.issue{margin:26px 0}.url{font-size:12px;color:#666;word-break:break-all}.reg{background:#fff7e6;border:1px solid #e3b75b;border-radius:8px;padding:16px;margin-top:14px}p{line-height:1.5}</style></head><body>",
        "<h1>Visual outreach evidence — strict + regulatory review</h1>",
        "<p>Regulatory context is included only where a visible issue maps credibly to the selected jurisdiction. Legal maximums are not estimates of the fine a business would actually receive.</p>",
    ]
    for row in rows:
        name = html.escape(_text(row.get("business_name")))
        evidence = row.get("evidence")
        parts.append(f"<section class='prospect'><h2>{name}</h2>")
        if not isinstance(evidence, list) or not evidence:
            parts.append("<p>No strong screenshot-ready issue captured.</p></section>")
            continue
        for item in evidence:
            if not isinstance(item, dict):
                continue
            src = html.escape(_text(item.get("screenshot_path")), quote=True)
            result_src = html.escape(_text(item.get("destination_screenshot_path")), quote=True)
            noticed = html.escape(_text(item.get("what_we_noticed")))
            impact = html.escape(_text(item.get("why_it_matters")))
            url = html.escape(_text(item.get("page_url")))
            parts.append(f"<article class='issue'><img src='{src}' alt='Source website evidence'>")
            if result_src:
                parts.append(f"<img src='{result_src}' alt='Failed destination evidence'>")
            parts.append(f"<h3>{noticed}</h3><p>{impact}</p><p class='url'>{url}</p>")
            regulatory = item.get("regulatory_relevance")
            if isinstance(regulatory, dict):
                parts.append("<div class='reg'><h4>Regulatory relevance</h4>")
                parts.append(f"<p>{html.escape(_text(regulatory.get('relevance')))}</p>")
                parts.append(f"<p><strong>Legal maximum exposure:</strong> {html.escape(_text(regulatory.get('legal_maximum_exposure')))}</p>")
                parts.append(f"<p><strong>Practical risk:</strong> {html.escape(_text(regulatory.get('practical_risk')))}</p>")
                parts.append(f"<p><strong>Estimated actual fine:</strong> {html.escape(_text(regulatory.get('estimated_actual_fine')))}</p></div>")
            parts.append("</article>")
        parts.append("</section>")
    parts.append("</body></html>")
    return "".join(parts)


def run(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    source = args.input or _latest_audit_zip(args.downloads)
    strict_args = [
        "--input", str(source),
        "--output-directory", str(args.output_directory),
        "--max-businesses", str(args.max_businesses),
        "--max-issues-per-business", str(args.max_issues_per_business),
        "--navigation-timeout-ms", str(args.navigation_timeout_ms),
    ]
    if strict_run(strict_args) != 0:
        return 1
    output = _latest_visual_zip(args.output_directory)
    with tempfile.TemporaryDirectory(prefix="veridra-regulatory-visual-") as temp_name:
        root = Path(temp_name)
        with zipfile.ZipFile(output) as archive:
            archive.extractall(root)
        rows_raw = json.loads((root / "visual_evidence.json").read_text(encoding="utf-8"))
        if not isinstance(rows_raw, list):
            raise ValueError("visual_evidence.json must contain a list.")
        rows = [row for row in rows_raw if isinstance(row, dict)]
        destination_count, regulatory_count = _augment_rows(
            rows=rows,
            root=root,
            country_code=args.country_code,
            timeout_ms=args.navigation_timeout_ms,
        )
        manifest_path = root / "manifest.json"
        manifest_raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest = manifest_raw if isinstance(manifest_raw, dict) else {}
        manifest["schema_version"] = 3
        manifest["country_code"] = args.country_code.strip().upper()
        manifest["failed_destination_screenshots"] = destination_count
        manifest["regulatory_context_count"] = regulatory_count
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        (root / "visual_evidence.json").write_text(
            json.dumps(rows, indent=2, sort_keys=True), encoding="utf-8"
        )
        (root / "summary.html").write_text(_summary(rows), encoding="utf-8")
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(root).as_posix())
    print(
        json.dumps(
            {
                "input": str(source),
                "output": str(output),
                "country_code": args.country_code.strip().upper(),
                "failed_destination_screenshots": destination_count,
                "regulatory_context_count": regulatory_count,
                "persistence": "none",
                "outreach": "none",
            },
            indent=2,
        )
    )
    return 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
