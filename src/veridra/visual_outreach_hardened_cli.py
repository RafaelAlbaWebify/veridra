from __future__ import annotations

import argparse
import json
import tempfile
import zipfile
from collections.abc import Sequence
from pathlib import Path

from playwright.sync_api import BrowserContext, Page, sync_playwright

from .visual_outreach_evidence_strict_cli import _safe_routes
from .visual_outreach_regulatory_cli import (
    _latest_visual_zip,
    _summary,
    regulatory_relevance,
)
from .visual_outreach_regulatory_cli import run as regulatory_run

_CHALLENGE_MARKERS = (
    "attention required | cloudflare",
    "cloudflare ray id",
    "checking your browser",
    "just a moment",
    "verify you are human",
    "security verification",
)


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


def quality_rejection_reason(*, title: str, visible_text: str, meaningful_elements: int) -> str:
    combined = f"{title}\n{visible_text}".casefold()
    if any(marker in combined for marker in _CHALLENGE_MARKERS):
        return "challenge_or_interstitial"
    compact = " ".join(visible_text.split())
    if len(compact) < 60 and meaningful_elements < 3:
        return "low_content_capture"
    return ""


def _page_quality_reason(page: Page) -> str:
    try:
        snapshot = page.evaluate(
            """
            () => {
              const visible = el => {
                const r = el.getBoundingClientRect();
                const s = getComputedStyle(el);
                return r.width > 8 && r.height > 8 && s.display !== 'none' && s.visibility !== 'hidden';
              };
              const meaningful = [...document.querySelectorAll('a,button,input,select,textarea,img,h1,h2,h3,p,li')]
                .filter(visible).length;
              return {
                title: document.title || '',
                text: document.body ? document.body.innerText || '' : '',
                meaningful
              };
            }
            """
        )
    except Exception:
        return "capture_unverifiable"
    if not isinstance(snapshot, dict):
        return "capture_unverifiable"
    return quality_rejection_reason(
        title=_text(snapshot.get("title")),
        visible_text=_text(snapshot.get("text")),
        meaningful_elements=_integer(snapshot.get("meaningful")),
    )


def _goto_status(page: Page, url: str, timeout_ms: int) -> int | None:
    try:
        response = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        page.wait_for_timeout(800)
    except Exception:
        return None
    return response.status if response is not None else None


def _capture_current_destination(
    page: Page, *, url: str, output: Path, timeout_ms: int, status_code: int
) -> bool:
    current = _goto_status(page, url, timeout_ms)
    if current is None or current != status_code:
        return False
    try:
        page.evaluate(
            """
            status => {
              document.querySelectorAll('[data-veridra-current-status]').forEach(el => el.remove());
              const badge = document.createElement('div');
              badge.setAttribute('data-veridra-current-status', '1');
              badge.textContent = `Destination currently returns HTTP ${status}`;
              badge.style.position = 'fixed';
              badge.style.left = '24px';
              badge.style.top = '24px';
              badge.style.zIndex = '2147483647';
              badge.style.background = '#d40000';
              badge.style.color = '#fff';
              badge.style.font = '700 18px Arial,sans-serif';
              badge.style.padding = '10px 14px';
              badge.style.borderRadius = '6px';
              document.body.appendChild(badge);
            }
            """,
            status_code,
        )
        page.screenshot(path=str(output), full_page=False)
        return True
    except Exception:
        return False


def _remove_evidence_files(root: Path, item: dict[str, object]) -> None:
    for key in ("screenshot_path", "destination_screenshot_path"):
        value = _text(item.get(key))
        if value:
            (root / value).unlink(missing_ok=True)


def _validate_visible_page(page: Page, url: str, timeout_ms: int) -> str:
    status = _goto_status(page, url, timeout_ms)
    if status is None:
        return "capture_unverifiable"
    return _page_quality_reason(page)


def _harden_rows(
    *,
    rows: list[dict[str, object]],
    root: Path,
    country_code: str,
    timeout_ms: int,
    context: BrowserContext,
) -> dict[str, int]:
    page = context.new_page()
    counters = {
        "unclear_form_suppressed": 0,
        "stale_broken_links_suppressed": 0,
        "quality_gate_suppressed": 0,
        "fresh_broken_links_verified": 0,
    }
    for row in rows:
        evidence = row.get("evidence")
        if not isinstance(evidence, list):
            row["evidence"] = []
            row["screenshot_ready_count"] = 0
            continue
        kept: list[dict[str, object]] = []
        for raw in evidence:
            if not isinstance(raw, dict):
                continue
            issue_type = _text(raw.get("issue_type"))
            if issue_type == "unclear_form":
                _remove_evidence_files(root, raw)
                counters["unclear_form_suppressed"] += 1
                continue

            page_url = _text(raw.get("page_url"))
            if page_url:
                quality_reason = _validate_visible_page(page, page_url, timeout_ms)
                if quality_reason:
                    raw["quality_rejection_reason"] = quality_reason
                    _remove_evidence_files(root, raw)
                    counters["quality_gate_suppressed"] += 1
                    continue

            if issue_type == "broken_link":
                details = raw.get("details")
                if not isinstance(details, dict):
                    _remove_evidence_files(root, raw)
                    counters["stale_broken_links_suppressed"] += 1
                    continue
                target_url = _text(details.get("target_url"))
                if not target_url:
                    _remove_evidence_files(root, raw)
                    counters["stale_broken_links_suppressed"] += 1
                    continue
                current_status = _goto_status(page, target_url, timeout_ms)
                if current_status is None or current_status < 400:
                    raw["fresh_verification"] = {
                        "status": current_status,
                        "result": "no_longer_reproduces" if current_status is not None else "unverifiable",
                    }
                    _remove_evidence_files(root, raw)
                    counters["stale_broken_links_suppressed"] += 1
                    continue
                details["status_code"] = current_status
                raw["fresh_verification"] = {"status": current_status, "result": "reproduced"}
                destination_rel = _text(raw.get("destination_screenshot_path"))
                if destination_rel:
                    destination_path = root / destination_rel
                else:
                    source_rel = Path(_text(raw.get("screenshot_path")))
                    destination_rel = source_rel.with_name(f"{source_rel.stem}-result.png").as_posix()
                    destination_path = root / destination_rel
                    raw["destination_screenshot_path"] = destination_rel
                destination_path.parent.mkdir(parents=True, exist_ok=True)
                if not _capture_current_destination(
                    page,
                    url=target_url,
                    output=destination_path,
                    timeout_ms=timeout_ms,
                    status_code=current_status,
                ):
                    _remove_evidence_files(root, raw)
                    counters["stale_broken_links_suppressed"] += 1
                    continue
                regulatory = regulatory_relevance(
                    country_code=country_code,
                    link_text=_text(details.get("link_text")),
                    target_url=target_url,
                    status_code=current_status,
                )
                if regulatory is None:
                    raw.pop("regulatory_relevance", None)
                else:
                    raw["regulatory_relevance"] = regulatory
                counters["fresh_broken_links_verified"] += 1

            kept.append(raw)
        row["evidence"] = kept
        row["screenshot_ready_count"] = len(kept)
    page.close()
    return counters


def _rewrite_zip(*, output: Path, country_code: str, timeout_ms: int) -> dict[str, int]:
    with tempfile.TemporaryDirectory(prefix="veridra-hardened-visual-") as temp_name:
        root = Path(temp_name)
        with zipfile.ZipFile(output) as archive:
            archive.extractall(root)
        rows_raw = json.loads((root / "visual_evidence.json").read_text(encoding="utf-8"))
        if not isinstance(rows_raw, list):
            raise ValueError("visual_evidence.json must contain a list.")
        rows = [row for row in rows_raw if isinstance(row, dict)]
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1280, "height": 900})
            _safe_routes(context)
            counters = _harden_rows(
                rows=rows,
                root=root,
                country_code=country_code,
                timeout_ms=timeout_ms,
                context=context,
            )
            context.close()
            browser.close()
        manifest_path = root / "manifest.json"
        manifest_raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest = manifest_raw if isinstance(manifest_raw, dict) else {}
        strong = sum(1 for row in rows if _integer(row.get("screenshot_ready_count")) > 0)
        issue_count = sum(_integer(row.get("screenshot_ready_count")) for row in rows)
        regulatory_count = 0
        for row in rows:
            evidence = row.get("evidence")
            if isinstance(evidence, list):
                regulatory_count += sum(
                    1
                    for item in evidence
                    if isinstance(item, dict) and isinstance(item.get("regulatory_relevance"), dict)
                )
        manifest.update(
            {
                "schema_version": 4,
                "businesses_with_strong_visual_evidence": strong,
                "strong_visual_issues": issue_count,
                "regulatory_context_count": regulatory_count,
                "hardening": counters,
                "scope": "freshly verified, contextual, visually self-evident outreach evidence only",
            }
        )
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        (root / "visual_evidence.json").write_text(
            json.dumps(rows, indent=2, sort_keys=True), encoding="utf-8"
        )
        (root / "summary.html").write_text(_summary(rows), encoding="utf-8")
        (root / "README.md").write_text(
            "# VERIDRA hardened visual evidence\n\n"
            "Evidence is revalidated immediately before packaging. Broken links that no longer "
            "reproduce are suppressed. Cloudflare/challenge and very low-content captures are "
            "suppressed. Generic form-label findings are not used as automatic outreach evidence.\n\n"
            "No outreach is sent and no prospect state is changed.\n",
            encoding="utf-8",
        )
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(root).as_posix())
    return counters


def run(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    forwarded = [
        "--downloads",
        str(args.downloads),
        "--output-directory",
        str(args.output_directory),
        "--max-businesses",
        str(args.max_businesses),
        "--max-issues-per-business",
        str(args.max_issues_per_business),
        "--navigation-timeout-ms",
        str(args.navigation_timeout_ms),
        "--country-code",
        args.country_code,
    ]
    if args.input is not None:
        forwarded.extend(["--input", str(args.input)])
    if regulatory_run(forwarded) != 0:
        return 1
    output = _latest_visual_zip(args.output_directory)
    counters = _rewrite_zip(
        output=output,
        country_code=args.country_code.strip().upper(),
        timeout_ms=args.navigation_timeout_ms,
    )
    print(
        json.dumps(
            {
                "output": str(output),
                "country_code": args.country_code.strip().upper(),
                **counters,
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
