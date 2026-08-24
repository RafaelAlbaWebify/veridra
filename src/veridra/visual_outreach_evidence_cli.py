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
from urllib.parse import urlsplit, urlunsplit

from playwright.sync_api import BrowserContext, Locator, Page, Request, Route, sync_playwright

from .core import UnsafeTargetError, resolve_public_ips

_PRIORITY = {
    "broken_link": 0,
    "mobile_overflow": 1,
    "form_control": 2,
    "interactive_control": 3,
}


@dataclass(frozen=True, slots=True)
class BusinessAudit:
    result_rank: int
    name: str
    audit_url: str
    assessment: dict[str, object]


@dataclass(frozen=True, slots=True)
class VisualEvidence:
    issue_type: str
    page_url: str
    screenshot_path: str
    what_we_noticed: str
    why_it_matters: str
    source_finding_id: str
    details: dict[str, object]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="veridra-visual-outreach-evidence")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--downloads", type=Path, default=Path.home() / "Downloads")
    parser.add_argument("--output-directory", type=Path, default=Path.home() / "Downloads")
    parser.add_argument("--max-businesses", type=int, default=15)
    parser.add_argument("--max-issues-per-business", type=int, default=3)
    parser.add_argument("--navigation-timeout-ms", type=int, default=20_000)
    return parser


def _latest_audit_zip(downloads: Path) -> Path:
    candidates = sorted(
        downloads.glob("VERIDRA_PROSPECT_AUDITS_*.zip"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError(f"No VERIDRA_PROSPECT_AUDITS_*.zip was found in {downloads}.")
    return candidates[0]


def _int_value(value: object, *, default: int = 0) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def _text_value(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _load_business_audits(path: Path, *, max_businesses: int) -> list[BusinessAudit]:
    if max_businesses < 1 or max_businesses > 100:
        raise ValueError("max-businesses must be between 1 and 100.")
    with zipfile.ZipFile(path) as archive:
        ranking_raw = json.loads(archive.read("audit_ranking.json"))
        if not isinstance(ranking_raw, list):
            raise ValueError("audit_ranking.json must contain a list.")
        values: list[BusinessAudit] = []
        for row in ranking_raw:
            if not isinstance(row, dict) or row.get("audit_status") != "success":
                continue
            rank = _int_value(row.get("result_rank"))
            if rank < 1:
                continue
            prefix = f"assessments/{rank:02d}-"
            names = [
                name
                for name in archive.namelist()
                if name.startswith(prefix) and name.endswith(".json")
            ]
            if not names:
                continue
            assessment = json.loads(archive.read(names[0]))
            if not isinstance(assessment, dict):
                continue
            values.append(
                BusinessAudit(
                    result_rank=rank,
                    name=_text_value(row.get("name")) or f"Business {rank}",
                    audit_url=_text_value(row.get("audit_url")),
                    assessment=assessment,
                )
            )
            if len(values) >= max_businesses:
                break
    if not values:
        raise ValueError("Audit ZIP contains no successful business assessments.")
    return values


def _canonical_http_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Expected an HTTP(S) URL with a hostname.")
    return urlunsplit(
        (
            parsed.scheme.casefold(),
            parsed.netloc.casefold(),
            parsed.path or "/",
            parsed.query,
            "",
        )
    )


def _safe_stem(value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-")
    return clean[:72] or "prospect"


def _finding_list(assessment: dict[str, object]) -> list[dict[str, object]]:
    raw = assessment.get("findings")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def _finding_by_id(assessment: dict[str, object], finding_id: str) -> dict[str, object] | None:
    return next(
        (finding for finding in _finding_list(assessment) if finding.get("id") == finding_id),
        None,
    )


def _evidence_dict(finding: dict[str, object] | None) -> dict[str, object]:
    if finding is None:
        return {}
    value = finding.get("evidence")
    return value if isinstance(value, dict) else {}


def _affected_urls(finding: dict[str, object] | None) -> list[str]:
    values = _evidence_dict(finding).get("affected_urls")
    if not isinstance(values, list):
        return []
    return [
        value
        for value in values
        if isinstance(value, str) and value.startswith(("http://", "https://"))
    ]


def _broken_targets(finding: dict[str, object] | None) -> list[dict[str, object]]:
    values = _evidence_dict(finding).get("broken_targets")
    if not isinstance(values, list):
        return []
    return [value for value in values if isinstance(value, dict)]


def _host_is_public(hostname: str, cache: dict[str, bool]) -> bool:
    folded = hostname.casefold().rstrip(".")
    cached = cache.get(folded)
    if cached is not None:
        return cached
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
    value = bool(ip.is_global)
    cache[folded] = value
    return value


def _install_safe_route(context: BrowserContext) -> None:
    cache: dict[str, bool] = {}

    def handler(route: Route, request: Request) -> None:
        parsed = urlsplit(request.url)
        if parsed.scheme in {"data", "blob", "about"}:
            route.continue_()
            return
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            route.abort()
            return
        if not _host_is_public(parsed.hostname, cache):
            route.abort()
            return
        route.continue_()

    context.route("**/*", handler)


def _goto(page: Page, url: str, *, timeout_ms: int) -> bool:
    try:
        _canonical_http_url(url)
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        page.wait_for_timeout(700)
    except Exception:
        return False
    return True


def _highlight(locator: Locator, label: str) -> None:
    locator.evaluate(
        """
        (el, label) => {
          el.scrollIntoView({block: 'center', inline: 'center'});
          el.style.setProperty('outline', '5px solid #d40000', 'important');
          el.style.setProperty('outline-offset', '4px', 'important');
          const badge = document.createElement('div');
          badge.textContent = label;
          badge.setAttribute('data-veridra-evidence-badge', '1');
          badge.style.position = 'absolute';
          badge.style.zIndex = '2147483647';
          badge.style.background = '#d40000';
          badge.style.color = 'white';
          badge.style.font = '700 16px Arial, sans-serif';
          badge.style.padding = '8px 10px';
          badge.style.borderRadius = '5px';
          const r = el.getBoundingClientRect();
          badge.style.left = `${Math.max(8, window.scrollX + r.left)}px`;
          badge.style.top = `${Math.max(8, window.scrollY + r.top - 44)}px`;
          document.body.appendChild(badge);
        }
        """,
        label,
    )


def _clear_highlights(page: Page) -> None:
    try:
        page.evaluate(
            """
            () => {
              document.querySelectorAll('[data-veridra-evidence-badge="1"]').forEach(el => el.remove());
              document.querySelectorAll('[data-veridra-evidence-target="1"]').forEach(el => {
                el.style.removeProperty('outline');
                el.style.removeProperty('outline-offset');
                el.removeAttribute('data-veridra-evidence-target');
              });
            }
            """
        )
    except Exception:
        return


def _capture_locator(page: Page, locator: Locator, path: Path, *, label: str) -> bool:
    try:
        locator.scroll_into_view_if_needed(timeout=3_000)
        locator.evaluate("el => el.setAttribute('data-veridra-evidence-target', '1')")
        _highlight(locator, label)
        page.wait_for_timeout(150)
        locator.screenshot(path=str(path))
        _clear_highlights(page)
        return True
    except Exception:
        _clear_highlights(page)
        return False


def _first_unlabelled_form_control(page: Page) -> int:
    value = page.evaluate(
        """
        () => {
          const els = [...document.querySelectorAll('input, select, textarea')];
          const visible = el => {
            const r = el.getBoundingClientRect();
            const s = getComputedStyle(el);
            return r.width > 8 && r.height > 8 && s.display !== 'none' && s.visibility !== 'hidden';
          };
          const named = el => {
            if (el.labels && el.labels.length) return true;
            if ((el.getAttribute('aria-label') || '').trim()) return true;
            if ((el.getAttribute('aria-labelledby') || '').trim()) return true;
            if ((el.getAttribute('title') || '').trim()) return true;
            return false;
          };
          return els.findIndex(el => {
            const type = (el.getAttribute('type') || '').toLowerCase();
            if (['hidden','submit','button','reset','image'].includes(type)) return false;
            return visible(el) && !named(el);
          });
        }
        """
    )
    return int(value) if isinstance(value, int) else -1


def _first_unnamed_interactive(page: Page) -> int:
    value = page.evaluate(
        """
        () => {
          const els = [...document.querySelectorAll('a[href], button, [role="button"]')];
          const visible = el => {
            const r = el.getBoundingClientRect();
            const s = getComputedStyle(el);
            return r.width > 8 && r.height > 8 && s.display !== 'none' && s.visibility !== 'hidden';
          };
          const named = el => {
            if ((el.innerText || '').trim()) return true;
            if ((el.getAttribute('aria-label') || '').trim()) return true;
            if ((el.getAttribute('aria-labelledby') || '').trim()) return true;
            if ((el.getAttribute('title') || '').trim()) return true;
            const img = el.querySelector('img[alt]');
            return Boolean(img && (img.getAttribute('alt') || '').trim());
          };
          return els.findIndex(el => visible(el) && !named(el));
        }
        """
    )
    return int(value) if isinstance(value, int) else -1


def _link_index_for_target(page: Page, target_url: str) -> int:
    value = page.evaluate(
        """
        target => {
          const clean = value => {
            try {
              const u = new URL(value, document.baseURI);
              u.hash = '';
              return u.href;
            } catch { return ''; }
          };
          const wanted = clean(target);
          return [...document.querySelectorAll('a[href]')].findIndex(a => clean(a.href) === wanted);
        }
        """,
        target_url,
    )
    return int(value) if isinstance(value, int) else -1


def _mobile_overflow(page: Page, url: str, *, timeout_ms: int) -> dict[str, object] | None:
    page.set_viewport_size({"width": 390, "height": 844})
    if not _goto(page, url, timeout_ms=timeout_ms):
        return None
    value = page.evaluate(
        """
        () => {
          const viewport = window.innerWidth;
          const doc = document.documentElement;
          if (doc.scrollWidth <= viewport + 5) return null;
          const all = [...document.querySelectorAll('body *')];
          const els = all.filter(el => {
            const r = el.getBoundingClientRect();
            const s = getComputedStyle(el);
            return r.width > 10 && r.height > 5 && s.display !== 'none' && s.visibility !== 'hidden' &&
                   (r.right > viewport + 5 || r.left < -5);
          }).sort((a, b) => b.getBoundingClientRect().right - a.getBoundingClientRect().right);
          const el = els[0];
          if (!el) return null;
          return {
            index: all.indexOf(el),
            scrollWidth: doc.scrollWidth,
            viewportWidth: viewport,
            tag: el.tagName,
            text: (el.innerText || '').trim().slice(0, 120)
          };
        }
        """
    )
    return value if isinstance(value, dict) else None


def _plain_text(issue_type: str) -> tuple[str, str]:
    if issue_type == "broken_link":
        return (
            "This link sends visitors to a page that does not work.",
            "A dead end can interrupt someone who is trying to find information or contact the clinic.",
        )
    if issue_type == "mobile_overflow":
        return (
            "Part of this page extends beyond a normal phone screen.",
            "Mobile visitors may need to scroll sideways or may miss content that should fit on screen.",
        )
    if issue_type == "form_control":
        return (
            "This form field is not clearly identified for every visitor.",
            "That can make the form harder to complete, especially for people using accessibility aids.",
        )
    return (
        "This clickable control is not clearly identified for every visitor.",
        "That can make navigation harder, especially for people using accessibility aids.",
    )


def _capture_broken_link(
    page: Page,
    target: dict[str, object],
    output_dir: Path,
    *,
    timeout_ms: int,
    index: int,
) -> VisualEvidence | None:
    target_url = _text_value(target.get("target_url"))
    sources = target.get("source_urls")
    if not target_url or not isinstance(sources, list):
        return None
    source_urls = [item for item in sources if isinstance(item, str)]
    for source_url in source_urls[:4]:
        page.set_viewport_size({"width": 1280, "height": 900})
        if not _goto(page, source_url, timeout_ms=timeout_ms):
            continue
        anchor_index = _link_index_for_target(page, target_url)
        if anchor_index < 0:
            continue
        locator = page.locator("a[href]").nth(anchor_index)
        filename = f"{index:02d}-broken-link.png"
        if not _capture_locator(page, locator, output_dir / filename, label="Link leads to a dead end"):
            continue
        noticed, impact = _plain_text("broken_link")
        return VisualEvidence(
            issue_type="broken_link",
            page_url=source_url,
            screenshot_path=filename,
            what_we_noticed=noticed,
            why_it_matters=impact,
            source_finding_id="crawl.broken-internal-links",
            details={
                "broken_target": target_url,
                "status_code": target.get("status_code"),
                "link_text": locator.inner_text(timeout=2_000).strip(),
            },
        )
    return None


def _capture_form_control(
    page: Page,
    page_url: str,
    output_dir: Path,
    *,
    timeout_ms: int,
    index: int,
) -> VisualEvidence | None:
    page.set_viewport_size({"width": 1280, "height": 900})
    if not _goto(page, page_url, timeout_ms=timeout_ms):
        return None
    control_index = _first_unlabelled_form_control(page)
    if control_index < 0:
        return None
    locator = page.locator("input, select, textarea").nth(control_index)
    filename = f"{index:02d}-form-field.png"
    if not _capture_locator(page, locator, output_dir / filename, label="Field is not clearly identified"):
        return None
    noticed, impact = _plain_text("form_control")
    return VisualEvidence(
        issue_type="form_control",
        page_url=page_url,
        screenshot_path=filename,
        what_we_noticed=noticed,
        why_it_matters=impact,
        source_finding_id="accessibility.form-labels",
        details={
            "tag": str(locator.evaluate("el => el.tagName")),
            "type": locator.get_attribute("type") or "",
            "placeholder": locator.get_attribute("placeholder") or "",
        },
    )


def _capture_interactive_control(
    page: Page,
    page_url: str,
    output_dir: Path,
    *,
    timeout_ms: int,
    index: int,
) -> VisualEvidence | None:
    page.set_viewport_size({"width": 1280, "height": 900})
    if not _goto(page, page_url, timeout_ms=timeout_ms):
        return None
    control_index = _first_unnamed_interactive(page)
    if control_index < 0:
        return None
    locator = page.locator('a[href], button, [role="button"]').nth(control_index)
    filename = f"{index:02d}-clickable-control.png"
    if not _capture_locator(page, locator, output_dir / filename, label="Clickable control has no clear name"):
        return None
    noticed, impact = _plain_text("interactive_control")
    return VisualEvidence(
        issue_type="interactive_control",
        page_url=page_url,
        screenshot_path=filename,
        what_we_noticed=noticed,
        why_it_matters=impact,
        source_finding_id="accessibility.interactive-names",
        details={"tag": str(locator.evaluate("el => el.tagName"))},
    )


def _capture_mobile_overflow(
    page: Page,
    business: BusinessAudit,
    output_dir: Path,
    *,
    timeout_ms: int,
    index: int,
) -> VisualEvidence | None:
    overflow = _mobile_overflow(page, business.audit_url, timeout_ms=timeout_ms)
    if overflow is None:
        return None
    body_index = _int_value(overflow.get("index"), default=-1)
    if body_index < 0:
        return None
    locator = page.locator("body *").nth(body_index)
    filename = f"{index:02d}-mobile-overflow.png"
    try:
        locator.evaluate("el => el.setAttribute('data-veridra-evidence-target', '1')")
        _highlight(locator, "Content extends beyond phone screen")
        page.screenshot(path=str(output_dir / filename), full_page=False)
        _clear_highlights(page)
    except Exception:
        _clear_highlights(page)
        return None
    noticed, impact = _plain_text("mobile_overflow")
    return VisualEvidence(
        issue_type="mobile_overflow",
        page_url=business.audit_url,
        screenshot_path=filename,
        what_we_noticed=noticed,
        why_it_matters=impact,
        source_finding_id="browser.mobile-overflow",
        details=overflow,
    )


def _business_evidence(
    page: Page,
    business: BusinessAudit,
    output_dir: Path,
    *,
    timeout_ms: int,
    max_issues: int,
) -> list[VisualEvidence]:
    output_dir.mkdir(parents=True, exist_ok=True)
    values: list[VisualEvidence] = []

    broken = _finding_by_id(business.assessment, "crawl.broken-internal-links")
    for target in _broken_targets(broken):
        item = _capture_broken_link(
            page,
            target,
            output_dir,
            timeout_ms=timeout_ms,
            index=len(values) + 1,
        )
        if item is not None:
            values.append(item)
            break

    if len(values) < max_issues:
        mobile = _capture_mobile_overflow(
            page,
            business,
            output_dir,
            timeout_ms=timeout_ms,
            index=len(values) + 1,
        )
        if mobile is not None:
            values.append(mobile)

    form = _finding_by_id(business.assessment, "accessibility.form-labels")
    if len(values) < max_issues and form is not None:
        for page_url in _affected_urls(form)[:5]:
            item = _capture_form_control(
                page,
                page_url,
                output_dir,
                timeout_ms=timeout_ms,
                index=len(values) + 1,
            )
            if item is not None:
                values.append(item)
                break

    interactive = _finding_by_id(business.assessment, "accessibility.interactive-names")
    if len(values) < max_issues and interactive is not None:
        for page_url in _affected_urls(interactive)[:5]:
            item = _capture_interactive_control(
                page,
                page_url,
                output_dir,
                timeout_ms=timeout_ms,
                index=len(values) + 1,
            )
            if item is not None:
                values.append(item)
                break

    return sorted(values, key=lambda item: _PRIORITY.get(item.issue_type, 99))[:max_issues]


def _html_summary(rows: list[dict[str, object]]) -> str:
    cards: list[str] = []
    for row in rows:
        business = html.escape(str(row["business_name"]))
        items = row.get("evidence")
        evidence_cards: list[str] = []
        if isinstance(items, list):
            for item in items:
                if not isinstance(item, dict):
                    continue
                screenshot = html.escape(str(item.get("screenshot_path", "")))
                noticed = html.escape(str(item.get("what_we_noticed", "")))
                impact = html.escape(str(item.get("why_it_matters", "")))
                page_url = html.escape(str(item.get("page_url", "")))
                evidence_cards.append(
                    "<article class='issue'>"
                    f"<img src='{screenshot}' alt='Annotated website evidence'>"
                    f"<h3>{noticed}</h3><p>{impact}</p>"
                    f"<p class='url'>{page_url}</p></article>"
                )
        cards.append(
            "<section class='prospect'>"
            f"<h2>{business}</h2>"
            + ("".join(evidence_cards) if evidence_cards else "<p>No screenshot-ready issue captured.</p>")
            + "</section>"
        )
    return """<!doctype html><html><head><meta charset='utf-8'><title>VERIDRA visual outreach evidence</title>
<style>body{font-family:Arial,sans-serif;max-width:1100px;margin:40px auto;padding:0 20px;color:#202124}
h1{font-size:30px}.prospect{margin:36px 0;padding-top:20px;border-top:1px solid #ddd}.issue{margin:24px 0}
img{max-width:100%;border:1px solid #ccc;border-radius:8px}.url{font-size:12px;color:#666;word-break:break-all}
h3{margin-bottom:6px}p{line-height:1.5}</style></head><body><h1>Visual outreach evidence</h1>
<p>Only screenshot-ready, user-facing observations are shown here. Technical-only findings are intentionally excluded.</p>""" + "".join(cards) + "</body></html>"


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True).encode("utf-8")


def _clear_temp_root(temp_root: Path) -> None:
    if not temp_root.exists():
        return
    for path in sorted(temp_root.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        if path.is_file():
            path.unlink()
        elif path.is_dir():
            path.rmdir()


def run(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.max_issues_per_business < 1 or args.max_issues_per_business > 5:
        raise ValueError("max-issues-per-business must be between 1 and 5.")
    input_path = args.input or _latest_audit_zip(args.downloads)
    businesses = _load_business_audits(input_path, max_businesses=args.max_businesses)

    temp_root = args.output_directory / ".veridra-visual-evidence"
    _clear_temp_root(temp_root)
    temp_root.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, object]] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        _install_safe_route(context)
        page = context.new_page()
        for position, business in enumerate(businesses, start=1):
            print(f"[Veridra] Visual evidence {position}/{len(businesses)}: {business.name}")
            folder_name = f"{business.result_rank:02d}-{_safe_stem(business.name)}"
            evidence = _business_evidence(
                page,
                business,
                temp_root / folder_name,
                timeout_ms=args.navigation_timeout_ms,
                max_issues=args.max_issues_per_business,
            )
            rows.append(
                {
                    "result_rank": business.result_rank,
                    "business_name": business.name,
                    "audit_url": business.audit_url,
                    "screenshot_ready_count": len(evidence),
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
                        for item in evidence
                    ],
                }
            )
        context.close()
        browser.close()

    generated_at = datetime.now(UTC).isoformat()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = args.output_directory / f"VERIDRA_VISUAL_EVIDENCE_{stamp}.zip"
    manifest = {
        "schema_version": 1,
        "generated_at": generated_at,
        "source_audit_zip": input_path.name,
        "businesses_reviewed": len(rows),
        "businesses_with_visual_evidence": sum(1 for row in rows if row["screenshot_ready_count"]),
        "screenshot_ready_issues": sum(_int_value(row["screenshot_ready_count"]) for row in rows),
        "persistence": "none",
        "outreach": "none",
        "scope": "screenshot-ready user-facing evidence only; technical-only findings excluded",
    }
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", _json_bytes(manifest))
        archive.writestr("visual_evidence.json", _json_bytes(rows))
        archive.writestr("summary.html", _html_summary(rows).encode("utf-8"))
        archive.writestr(
            "README.md",
            (
                "# VERIDRA visual outreach evidence\n\n"
                "This package contains screenshot-ready, user-facing observations only. "
                "Technical-only audit findings are intentionally excluded from outreach evidence.\n\n"
                "No outreach is sent and no prospect state is persisted.\n"
            ).encode("utf-8"),
        )
        for path in temp_root.rglob("*.png"):
            archive.write(path, path.relative_to(temp_root).as_posix())

    print(
        json.dumps(
            {
                "input": str(input_path),
                "output": str(output_path),
                "businesses_reviewed": len(rows),
                "businesses_with_visual_evidence": manifest["businesses_with_visual_evidence"],
                "screenshot_ready_issues": manifest["screenshot_ready_issues"],
                "persistence": "none",
                "outreach": "none",
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
