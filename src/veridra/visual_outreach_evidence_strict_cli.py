from __future__ import annotations

import argparse
import html
import ipaddress
import json
import re
import socket
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import BrowserContext, Locator, Page, Request, Route, sync_playwright

from .core import UnsafeTargetError, resolve_public_ips


@dataclass(frozen=True, slots=True)
class BusinessAudit:
    result_rank: int
    name: str
    audit_url: str
    assessment: dict[str, object]


@dataclass(frozen=True, slots=True)
class Evidence:
    issue_type: str
    page_url: str
    screenshot_path: str
    what_we_noticed: str
    why_it_matters: str
    source_finding_id: str
    details: dict[str, object]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="veridra-visual-outreach-evidence-strict")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--downloads", type=Path, default=Path.home() / "Downloads")
    parser.add_argument("--output-directory", type=Path, default=Path.home() / "Downloads")
    parser.add_argument("--max-businesses", type=int, default=15)
    parser.add_argument("--max-issues-per-business", type=int, default=3)
    parser.add_argument("--navigation-timeout-ms", type=int, default=20_000)
    return parser


def _latest_audit_zip(downloads: Path) -> Path:
    values = sorted(
        downloads.glob("VERIDRA_PROSPECT_AUDITS_*.zip"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not values:
        raise FileNotFoundError(f"No VERIDRA_PROSPECT_AUDITS_*.zip was found in {downloads}.")
    return values[0]


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _integer(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _safe_stem(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-")[:72] or "prospect"


def _load(path: Path, *, max_businesses: int) -> list[BusinessAudit]:
    with zipfile.ZipFile(path) as archive:
        ranking = json.loads(archive.read("audit_ranking.json"))
        if not isinstance(ranking, list):
            raise ValueError("audit_ranking.json must contain a list.")
        results: list[BusinessAudit] = []
        for row in ranking:
            if not isinstance(row, dict) or row.get("audit_status") != "success":
                continue
            rank = _integer(row.get("result_rank"))
            prefix = f"assessments/{rank:02d}-"
            names = [n for n in archive.namelist() if n.startswith(prefix) and n.endswith(".json")]
            if rank < 1 or not names:
                continue
            assessment = json.loads(archive.read(names[0]))
            if not isinstance(assessment, dict):
                continue
            results.append(
                BusinessAudit(
                    result_rank=rank,
                    name=_text(row.get("name")) or f"Business {rank}",
                    audit_url=_text(row.get("audit_url")),
                    assessment=assessment,
                )
            )
            if len(results) >= max_businesses:
                break
    return results


def _find(assessment: dict[str, object], finding_id: str) -> dict[str, object] | None:
    findings = assessment.get("findings")
    if not isinstance(findings, list):
        return None
    for finding in findings:
        if isinstance(finding, dict) and finding.get("id") == finding_id:
            return finding
    return None


def _evidence(finding: dict[str, object] | None) -> dict[str, object]:
    if not finding:
        return {}
    value = finding.get("evidence")
    return value if isinstance(value, dict) else {}


def _public_host(hostname: str, cache: dict[str, bool]) -> bool:
    folded = hostname.casefold().rstrip(".")
    if folded in cache:
        return cache[folded]
    try:
        ip = ipaddress.ip_address(folded)
    except ValueError:
        try:
            resolve_public_ips(folded)
        except (UnsafeTargetError, OSError, socket.gaierror):
            cache[folded] = False
            return False
        cache[folded] = True
        return True
    cache[folded] = bool(ip.is_global)
    return cache[folded]


def _safe_routes(context: BrowserContext) -> None:
    cache: dict[str, bool] = {}

    def handler(route: Route, request: Request) -> None:
        parsed = urlsplit(request.url)
        if parsed.scheme in {"data", "blob", "about"}:
            route.continue_()
            return
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            route.abort()
            return
        if not _public_host(parsed.hostname, cache):
            route.abort()
            return
        route.continue_()

    context.route("**/*", handler)


def _goto(page: Page, url: str, timeout_ms: int) -> bool:
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return False
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        page.wait_for_timeout(800)
        return True
    except Exception:
        return False


def _highlight(locator: Locator, label: str) -> None:
    locator.evaluate(
        """
        (el, label) => {
          el.scrollIntoView({block:'center', inline:'center'});
          el.setAttribute('data-veridra-target','1');
          el.style.setProperty('outline','5px solid #d40000','important');
          el.style.setProperty('outline-offset','4px','important');
          const badge=document.createElement('div');
          badge.setAttribute('data-veridra-badge','1');
          badge.textContent=label;
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
        label,
    )


def _clear(page: Page) -> None:
    try:
        page.evaluate(
            """
            () => {
              document.querySelectorAll('[data-veridra-badge="1"]').forEach(el=>el.remove());
              document.querySelectorAll('[data-veridra-target="1"]').forEach(el=>{
                el.style.removeProperty('outline');
                el.style.removeProperty('outline-offset');
                el.removeAttribute('data-veridra-target');
              });
            }
            """
        )
    except Exception:
        pass


def _context_screenshot(page: Page, locator: Locator, path: Path, label: str) -> bool:
    try:
        locator.scroll_into_view_if_needed(timeout=3_000)
        _highlight(locator, label)
        page.wait_for_timeout(150)
        box = locator.bounding_box()
        if box is None:
            return False
        viewport = page.viewport_size or {"width": 1280, "height": 900}
        x = max(0.0, box["x"] - 260.0)
        y = max(0.0, box["y"] - 220.0)
        width = min(float(viewport["width"]) - x, max(760.0, box["width"] + 520.0))
        height = min(float(viewport["height"]) - y, max(520.0, box["height"] + 440.0))
        if width < 600 or height < 350:
            page.screenshot(path=str(path), full_page=False)
        else:
            page.screenshot(path=str(path), clip={"x": x, "y": y, "width": width, "height": height})
        _clear(page)
        return True
    except Exception:
        _clear(page)
        return False


def _broken_targets(assessment: dict[str, object]) -> list[dict[str, object]]:
    values = _evidence(_find(assessment, "crawl.broken-internal-links")).get("broken_targets")
    return [item for item in values if isinstance(item, dict)] if isinstance(values, list) else []


def _link_index(page: Page, target_url: str) -> int:
    value = page.evaluate(
        """
        target => {
          const norm=v=>{try{const u=new URL(v,document.baseURI);u.hash='';return u.href}catch{return ''}};
          const wanted=norm(target);
          return [...document.querySelectorAll('a[href]')].findIndex(a=>norm(a.href)===wanted);
        }
        """,
        target_url,
    )
    return value if isinstance(value, int) else -1


def _capture_broken(page: Page, target: dict[str, object], directory: Path, timeout_ms: int, index: int) -> Evidence | None:
    target_url = _text(target.get("target_url"))
    sources = target.get("source_urls")
    if not target_url or not isinstance(sources, list):
        return None
    for source in [s for s in sources if isinstance(s, str)][:4]:
        page.set_viewport_size({"width": 1280, "height": 900})
        if not _goto(page, source, timeout_ms):
            continue
        link_index = _link_index(page, target_url)
        if link_index < 0:
            continue
        locator = page.locator("a[href]").nth(link_index)
        text = locator.inner_text(timeout=2_000).strip()
        if not text:
            continue
        filename = f"{index:02d}-dead-end.png"
        if not _context_screenshot(page, locator, directory / filename, "This link leads to a dead end"):
            continue
        return Evidence(
            issue_type="broken_link",
            page_url=source,
            screenshot_path=filename,
            what_we_noticed=f"The visible link ‘{text[:80]}’ leads to a page that does not work.",
            why_it_matters="A visitor can hit a dead end while trying to continue through the website.",
            source_finding_id="crawl.broken-internal-links",
            details={"target_url": target_url, "link_text": text, "status_code": target.get("status_code")},
        )
    return None


def _blank_form_index(page: Page) -> int:
    value = page.evaluate(
        """
        () => {
          const els=[...document.querySelectorAll('input,select,textarea')];
          const visible=el=>{const r=el.getBoundingClientRect(),s=getComputedStyle(el);return r.width>80&&r.height>24&&s.display!=='none'&&s.visibility!=='hidden'};
          const labelled=el=>Boolean((el.labels&&el.labels.length)||(el.getAttribute('aria-label')||'').trim()||(el.getAttribute('aria-labelledby')||'').trim()||(el.getAttribute('title')||'').trim()||(el.getAttribute('placeholder')||'').trim());
          return els.findIndex(el=>{const type=(el.getAttribute('type')||'').toLowerCase();return visible(el)&&!['hidden','submit','button','reset','image'].includes(type)&&!labelled(el)});
        }
        """
    )
    return value if isinstance(value, int) else -1


def _capture_blank_form(page: Page, page_url: str, directory: Path, timeout_ms: int, index: int) -> Evidence | None:
    page.set_viewport_size({"width": 1280, "height": 900})
    if not _goto(page, page_url, timeout_ms):
        return None
    position = _blank_form_index(page)
    if position < 0:
        return None
    locator = page.locator("input,select,textarea").nth(position)
    filename = f"{index:02d}-unclear-form.png"
    if not _context_screenshot(page, locator, directory / filename, "This field has no visible explanation"):
        return None
    return Evidence(
        issue_type="unclear_form",
        page_url=page_url,
        screenshot_path=filename,
        what_we_noticed="This form contains a field with no visible label or instruction telling the visitor what to enter.",
        why_it_matters="That creates unnecessary uncertainty at the point where a visitor is trying to complete the form.",
        source_finding_id="accessibility.form-labels",
        details={"type": locator.get_attribute("type") or "", "placeholder": ""},
    )


def _overflow(page: Page, url: str, timeout_ms: int) -> tuple[Locator, dict[str, object]] | None:
    page.set_viewport_size({"width": 390, "height": 844})
    if not _goto(page, url, timeout_ms):
        return None
    value = page.evaluate(
        """
        () => {
          const vw=window.innerWidth, all=[...document.querySelectorAll('body *')];
          if(document.documentElement.scrollWidth<=vw+12)return null;
          const candidates=all.map((el,i)=>({el,i,r:el.getBoundingClientRect(),s:getComputedStyle(el)})).filter(x=>x.r.width>40&&x.r.height>20&&x.s.display!=='none'&&x.s.visibility!=='hidden'&&(x.r.right>vw+20||x.r.left<-20));
          if(!candidates.length)return null;
          candidates.sort((a,b)=>(b.r.right-vw)-(a.r.right-vw));
          const x=candidates[0];
          return {index:x.i,scrollWidth:document.documentElement.scrollWidth,viewportWidth:vw,tag:x.el.tagName};
        }
        """
    )
    if not isinstance(value, dict) or not isinstance(value.get("index"), int):
        return None
    return page.locator("body *").nth(value["index"]), value


def _capture_overflow(page: Page, business: BusinessAudit, directory: Path, timeout_ms: int, index: int) -> Evidence | None:
    found = _overflow(page, business.audit_url, timeout_ms)
    if found is None:
        return None
    locator, details = found
    filename = f"{index:02d}-mobile-overflow.png"
    if not _context_screenshot(page, locator, directory / filename, "Content extends beyond the phone screen"):
        return None
    return Evidence(
        issue_type="mobile_overflow",
        page_url=business.audit_url,
        screenshot_path=filename,
        what_we_noticed="Part of this page extends beyond a normal phone screen instead of fitting inside it.",
        why_it_matters="A mobile visitor may need to scroll sideways or may miss information that should be visible immediately.",
        source_finding_id="runtime.mobile-overflow",
        details=details,
    )


def _affected_form_urls(assessment: dict[str, object]) -> list[str]:
    values = _evidence(_find(assessment, "accessibility.form-labels")).get("affected_urls")
    if not isinstance(values, list):
        return []
    return [v for v in values if isinstance(v, str) and v.startswith(("http://", "https://"))]


def _html_summary(rows: list[dict[str, object]]) -> str:
    parts = ["<!doctype html><html><head><meta charset='utf-8'><title>VERIDRA visual evidence</title>", "<style>body{font-family:Arial,sans-serif;max-width:1100px;margin:40px auto;padding:0 20px;color:#202124}img{max-width:100%;border:1px solid #ccc;border-radius:8px}.prospect{margin:38px 0;padding-top:22px;border-top:1px solid #ddd}.issue{margin:26px 0}.url{font-size:12px;color:#666;word-break:break-all}p{line-height:1.5}</style></head><body>", "<h1>Visual outreach evidence — strict review</h1>", "<p>Only issues that can be shown with page context and explained in plain business language are included.</p>"]
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
            noticed = html.escape(_text(item.get("what_we_noticed")))
            impact = html.escape(_text(item.get("why_it_matters")))
            url = html.escape(_text(item.get("page_url")))
            parts.append(f"<article class='issue'><img src='{src}' alt='Annotated website evidence'><h3>{noticed}</h3><p>{impact}</p><p class='url'>{url}</p></article>")
        parts.append("</section>")
    parts.append("</body></html>")
    return "".join(parts)


def run(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    source = args.input or _latest_audit_zip(args.downloads)
    businesses = _load(source, max_businesses=args.max_businesses)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    temp_root = args.output_directory / f".veridra-visual-strict-{timestamp}"
    temp_root.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        _safe_routes(context)
        page = context.new_page()
        for business in businesses:
            print(f"[Veridra] Visual strict review {business.result_rank}: {business.name}")
            folder_name = f"{business.result_rank:02d}-{_safe_stem(business.name)}"
            folder = temp_root / folder_name
            folder.mkdir(parents=True, exist_ok=True)
            captured: list[Evidence] = []
            for target in _broken_targets(business.assessment):
                if len(captured) >= args.max_issues_per_business:
                    break
                item = _capture_broken(page, target, folder, args.navigation_timeout_ms, len(captured) + 1)
                if item:
                    captured.append(item)
            if len(captured) < args.max_issues_per_business:
                item = _capture_overflow(page, business, folder, args.navigation_timeout_ms, len(captured) + 1)
                if item:
                    captured.append(item)
            for url in _affected_form_urls(business.assessment)[:4]:
                if len(captured) >= args.max_issues_per_business:
                    break
                item = _capture_blank_form(page, url, folder, args.navigation_timeout_ms, len(captured) + 1)
                if item:
                    captured.append(item)
                    break
            rows.append({
                "result_rank": business.result_rank,
                "business_name": business.name,
                "audit_url": business.audit_url,
                "screenshot_ready_count": len(captured),
                "evidence": [
                    {
                        "issue_type": item.issue_type,
                        "page_url": item.page_url,
                        "screenshot_path": f"{folder_name}/{item.screenshot_path}",
                        "what_we_noticed": item.what_we_noticed,
                        "why_it_matters": item.why_it_matters,
                        "source_finding_id": item.source_finding_id,
                        "details": item.details,
                    }
                    for item in captured
                ],
            })
        context.close()
        browser.close()
    strong = sum(1 for row in rows if _integer(row.get("screenshot_ready_count")) > 0)
    issue_count = sum(_integer(row.get("screenshot_ready_count")) for row in rows)
    manifest = {
        "schema_version": 2,
        "generated_at": datetime.now(UTC).isoformat(),
        "source_audit_zip": source.name,
        "businesses_reviewed": len(rows),
        "businesses_with_strong_visual_evidence": strong,
        "strong_visual_issues": issue_count,
        "scope": "contextual, visually self-evident outreach evidence only",
        "persistence": "none",
        "outreach": "none",
    }
    output = args.output_directory / f"VERIDRA_VISUAL_EVIDENCE_STRICT_{timestamp}.zip"
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True))
        archive.writestr("visual_evidence.json", json.dumps(rows, indent=2, sort_keys=True))
        archive.writestr("summary.html", _html_summary(rows))
        archive.writestr("README.md", "# VERIDRA strict visual evidence\n\nOnly contextual, visibly understandable issues are included. Generic technical/accessibility implementation findings are excluded from outreach evidence unless the problem itself is visibly unclear to a visitor.\n\nNo outreach is sent and no state is persisted.\n")
        for screenshot in temp_root.rglob("*.png"):
            archive.write(screenshot, screenshot.relative_to(temp_root).as_posix())
    for screenshot in temp_root.rglob("*.png"):
        screenshot.unlink(missing_ok=True)
    for directory in sorted(temp_root.rglob("*"), reverse=True):
        if directory.is_dir():
            directory.rmdir()
    temp_root.rmdir()
    print(json.dumps({"input": str(source), "output": str(output), "businesses_reviewed": len(rows), "businesses_with_strong_visual_evidence": strong, "strong_visual_issues": issue_count, "persistence": "none", "outreach": "none"}, indent=2))
    return 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
