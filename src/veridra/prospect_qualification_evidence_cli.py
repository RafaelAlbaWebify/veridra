from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import zipfile
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from .collector import PageEvidence, collect_page

_RELEVANT_LINK_TERMS = (
    "contact",
    "about",
    "team",
    "staff",
    "dentist",
    "doctor",
    "practice",
    "clinic",
    "location",
    "book",
    "appointment",
)
_ROLE_TERMS = (
    "owner",
    "founder",
    "principal dentist",
    "practice manager",
    "clinical director",
    "managing director",
    "director",
)
_GROUP_TERMS = (
    "our clinics",
    "our locations",
    "multiple locations",
    "part of the",
    "part of",
    "dental group",
    "clinic group",
    "network of clinics",
    "branches",
)
_SOCIAL_HOSTS = (
    "linkedin.com",
    "facebook.com",
    "instagram.com",
    "twitter.com",
    "x.com",
)
_APPOINTMENT_TERMS = ("book", "appointment", "consultation", "contact")
_EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class QualificationTarget:
    result_rank: int
    name: str
    audit_url: str
    audit_status: str
    technical_finding_weight: int | None
    attention_findings: int
    shared_hostname: bool


@dataclass(frozen=True, slots=True)
class PageSignals:
    url: str
    status_code: int
    emails: tuple[str, ...]
    phones: tuple[str, ...]
    social_urls: tuple[str, ...]
    appointment_urls: tuple[str, ...]
    role_snippets: tuple[str, ...]
    group_snippets: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class QualificationOutcome:
    target: QualificationTarget
    pages: tuple[PageSignals, ...]
    top_audit_findings: tuple[dict[str, str], ...]
    errors: tuple[str, ...]


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self.text_chunks: list[str] = []
        self._anchor_href: str | None = None
        self._anchor_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        data = {key.casefold(): (value or "") for key, value in attrs}
        self._anchor_href = data.get("href", "").strip()
        self._anchor_text = []

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if not text:
            return
        self.text_chunks.append(text)
        if self._anchor_href is not None:
            self._anchor_text.append(text)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or self._anchor_href is None:
            return
        self.links.append((self._anchor_href, " ".join(self._anchor_text).strip()))
        self._anchor_href = None
        self._anchor_text = []


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="veridra-prospect-qualification-evidence")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--downloads", type=Path, default=Path.home() / "Downloads")
    parser.add_argument("--output-directory", type=Path, default=Path.home() / "Downloads")
    parser.add_argument("--max-targets", type=int, default=20)
    parser.add_argument("--max-pages-per-site", type=int, default=4)
    return parser


def _latest_audit_zip(downloads: Path) -> Path:
    candidates = sorted(
        downloads.glob("VERIDRA_PROSPECT_AUDITS_*.zip"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError(
            f"No VERIDRA_PROSPECT_AUDITS_*.zip file was found in {downloads}."
        )
    return candidates[0]


def _int_value(value: object, *, default: int = 0) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _load_targets(path: Path, *, max_targets: int) -> list[QualificationTarget]:
    if not 1 <= max_targets <= 100:
        raise ValueError("max-targets must be between 1 and 100.")
    with zipfile.ZipFile(path) as archive:
        raw = json.loads(archive.read("audit_ranking.json"))
    if not isinstance(raw, list):
        raise ValueError("audit_ranking.json must contain a list.")
    targets: list[QualificationTarget] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        name = row.get("name")
        audit_url = row.get("audit_url")
        if not isinstance(name, str) or not isinstance(audit_url, str):
            continue
        targets.append(
            QualificationTarget(
                result_rank=_int_value(row.get("result_rank"), default=len(targets) + 1),
                name=name.strip() or audit_url,
                audit_url=audit_url,
                audit_status=str(row.get("audit_status", "unknown")),
                technical_finding_weight=_optional_int(row.get("technical_finding_weight")),
                attention_findings=_int_value(row.get("attention_findings")),
                shared_hostname=bool(row.get("shared_hostname", False)),
            )
        )
        if len(targets) >= max_targets:
            break
    if not targets:
        raise ValueError("Audit ZIP contains no qualification targets.")
    return targets


def _same_host(base_url: str, candidate_url: str) -> bool:
    base_host = (urlsplit(base_url).hostname or "").casefold()
    candidate_host = (urlsplit(candidate_url).hostname or "").casefold()
    return bool(base_host and base_host == candidate_host)


def _interesting_internal_links(base_url: str, parser: _PageParser) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for href, text in parser.links:
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        resolved = urljoin(base_url, href)
        if not _same_host(base_url, resolved):
            continue
        folded = f"{urlsplit(resolved).path} {text}".casefold()
        if not any(term in folded for term in _RELEVANT_LINK_TERMS):
            continue
        normalized = resolved.split("#", 1)[0]
        if normalized in seen:
            continue
        seen.add(normalized)
        values.append(normalized)
    return values


def _bounded_snippets(chunks: Sequence[str], terms: Sequence[str]) -> tuple[str, ...]:
    values: list[str] = []
    seen: set[str] = set()
    for chunk in chunks:
        folded = chunk.casefold()
        if not any(term in folded for term in terms):
            continue
        clean = " ".join(chunk.split())[:240]
        if len(clean) < 3 or clean.casefold() in seen:
            continue
        seen.add(clean.casefold())
        values.append(clean)
        if len(values) >= 12:
            break
    return tuple(values)


def _page_signals(page: PageEvidence) -> tuple[PageSignals, list[str]]:
    parser = _PageParser()
    parser.feed(page.body)
    emails: set[str] = set(_EMAIL_RE.findall(page.body))
    phones: set[str] = set()
    social_urls: set[str] = set()
    appointment_urls: set[str] = set()
    for href, text in parser.links:
        folded_href = href.casefold()
        if folded_href.startswith("mailto:"):
            email = href.split(":", 1)[1].split("?", 1)[0].strip()
            if email:
                emails.add(email)
            continue
        if folded_href.startswith("tel:"):
            phone = href.split(":", 1)[1].strip()
            if phone:
                phones.add(phone)
            continue
        resolved = urljoin(page.final_url, href)
        hostname = (urlsplit(resolved).hostname or "").casefold()
        if any(hostname == social or hostname.endswith(f".{social}") for social in _SOCIAL_HOSTS):
            social_urls.add(resolved.split("#", 1)[0])
        folded = f"{href} {text}".casefold()
        if any(term in folded for term in _APPOINTMENT_TERMS):
            appointment_urls.add(resolved.split("#", 1)[0])
    signals = PageSignals(
        url=page.final_url,
        status_code=page.status_code,
        emails=tuple(sorted(emails)),
        phones=tuple(sorted(phones)),
        social_urls=tuple(sorted(social_urls)),
        appointment_urls=tuple(sorted(appointment_urls)),
        role_snippets=_bounded_snippets(parser.text_chunks, _ROLE_TERMS),
        group_snippets=_bounded_snippets(parser.text_chunks, _GROUP_TERMS),
    )
    return signals, _interesting_internal_links(page.final_url, parser)


def _audit_findings_for_target(archive: zipfile.ZipFile, target: QualificationTarget) -> tuple[dict[str, str], ...]:
    prefix = f"assessments/{target.result_rank:02d}-"
    names = [name for name in archive.namelist() if name.startswith(prefix) and name.endswith(".json")]
    if not names:
        return ()
    payload = json.loads(archive.read(names[0]))
    findings = payload.get("findings", []) if isinstance(payload, dict) else []
    values: list[dict[str, str]] = []
    if not isinstance(findings, list):
        return ()
    for finding in findings:
        if not isinstance(finding, dict) or finding.get("status") != "attention":
            continue
        values.append(
            {
                "id": str(finding.get("id", "")),
                "severity": str(finding.get("severity", "")),
                "area": str(finding.get("area", "")),
                "title": str(finding.get("title", "")),
                "summary": str(finding.get("summary", "")),
            }
        )
        if len(values) >= 8:
            break
    return tuple(values)


Collector = Callable[[str], PageEvidence]


def qualify_target(
    target: QualificationTarget,
    *,
    collector: Collector = collect_page,
    max_pages: int = 4,
    top_audit_findings: tuple[dict[str, str], ...] = (),
) -> QualificationOutcome:
    if not 1 <= max_pages <= 10:
        raise ValueError("max-pages-per-site must be between 1 and 10.")
    queue = [target.audit_url]
    visited: set[str] = set()
    pages: list[PageSignals] = []
    errors: list[str] = []
    while queue and len(visited) < max_pages:
        url = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)
        try:
            page = collector(url)
        except Exception as exc:
            errors.append(f"{url}: {exc}")
            continue
        signals, links = _page_signals(page)
        pages.append(signals)
        for link in links:
            if link not in visited and link not in queue and len(queue) < max_pages * 3:
                queue.append(link)
    return QualificationOutcome(
        target=target,
        pages=tuple(pages),
        top_audit_findings=top_audit_findings,
        errors=tuple(errors),
    )


def _aggregate(outcome: QualificationOutcome) -> dict[str, object]:
    emails = sorted({value for page in outcome.pages for value in page.emails})
    phones = sorted({value for page in outcome.pages for value in page.phones})
    social_urls = sorted({value for page in outcome.pages for value in page.social_urls})
    appointment_urls = sorted({value for page in outcome.pages for value in page.appointment_urls})
    role_snippets = list(dict.fromkeys(value for page in outcome.pages for value in page.role_snippets))
    group_snippets = list(dict.fromkeys(value for page in outcome.pages for value in page.group_snippets))
    reachable_pages = sum(1 for page in outcome.pages if 200 <= page.status_code < 400)
    contact_route = bool(emails or phones or appointment_urls)
    review_reasons: list[str] = []
    if reachable_pages == 0:
        review_reasons.append("No reachable website page was collected.")
    if not contact_route:
        review_reasons.append("No direct email, phone, or appointment/contact route was captured.")
    if outcome.target.shared_hostname:
        review_reasons.append("Website hostname is shared by multiple discovered business listings.")
    if group_snippets:
        review_reasons.append("Website contains possible group or multi-location language; verify manually.")
    if outcome.target.audit_status != "success":
        review_reasons.append("Prior technical audit did not complete successfully.")
    return {
        "result_rank": outcome.target.result_rank,
        "name": outcome.target.name,
        "audit_url": outcome.target.audit_url,
        "audit_status": outcome.target.audit_status,
        "technical_finding_weight": outcome.target.technical_finding_weight,
        "attention_findings": outcome.target.attention_findings,
        "shared_hostname": outcome.target.shared_hostname,
        "reachable_pages": reachable_pages,
        "pages_collected": len(outcome.pages),
        "emails": emails,
        "phones": phones,
        "social_urls": social_urls,
        "appointment_urls": appointment_urls,
        "role_snippets": role_snippets,
        "group_snippets": group_snippets,
        "top_audit_findings": list(outcome.top_audit_findings),
        "review_state": "ready_for_manual_qualification" if reachable_pages and contact_route else "needs_manual_review",
        "review_reasons": review_reasons,
        "errors": list(outcome.errors),
    }


def _csv_bytes(rows: Sequence[dict[str, object]]) -> bytes:
    buffer = io.StringIO(newline="")
    fieldnames = [
        "result_rank",
        "name",
        "audit_url",
        "audit_status",
        "technical_finding_weight",
        "attention_findings",
        "shared_hostname",
        "reachable_pages",
        "pages_collected",
        "emails",
        "phones",
        "appointment_urls",
        "role_snippets",
        "group_snippets",
        "review_state",
        "review_reasons",
        "errors",
    ]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                key: " | ".join(str(item) for item in value) if isinstance(value, list) else value
                for key, value in row.items()
                if key in fieldnames
            }
        )
    return buffer.getvalue().encode("utf-8-sig")


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_name(value: str) -> str:
    clean = "".join(character if character.isalnum() else "-" for character in value)
    return "-".join(part for part in clean.split("-") if part)[:80] or "prospect"


def _build_archive(
    *,
    source_path: Path,
    outcomes: Sequence[QualificationOutcome],
    generated_at: str,
    max_pages_per_site: int,
) -> bytes:
    rows = [_aggregate(outcome) for outcome in outcomes]
    manifest = {
        "schema_version": 1,
        "generated_at": generated_at,
        "source_audit_zip": source_path.name,
        "source_audit_sha256": _sha256_file(source_path),
        "business_targets": len(outcomes),
        "ready_for_manual_qualification": sum(
            1 for row in rows if row["review_state"] == "ready_for_manual_qualification"
        ),
        "needs_manual_review": sum(1 for row in rows if row["review_state"] == "needs_manual_review"),
        "max_pages_per_site": max_pages_per_site,
        "persistence": "none",
        "outreach": "none",
        "interpretation_boundary": (
            "Role and group snippets are public website evidence for human review, not verified "
            "ownership or corporate-structure facts. No commercial propensity score is produced."
        ),
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", _json_bytes(manifest))
        archive.writestr("qualification_summary.json", _json_bytes(rows))
        archive.writestr("qualification_summary.csv", _csv_bytes(rows))
        archive.writestr(
            "README.md",
            b"# VERIDRA commercial qualification evidence\n\n"
            b"Read-only public website evidence collected after technical audit.\n\n"
            b"Contact routes are extracted facts. Role and group snippets are review clues only; "
            b"they are not verified ownership or corporate-structure conclusions. No prospects "
            b"are persisted and no outreach is performed.\n",
        )
        for outcome, row in zip(outcomes, rows, strict=True):
            stem = f"{outcome.target.result_rank:02d}-{_safe_name(outcome.target.name)}"
            archive.writestr(
                f"prospects/{stem}.json",
                _json_bytes({"summary": row, "pages": [asdict(page) for page in outcome.pages]}),
            )
    return buffer.getvalue()


def run(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not 1 <= args.max_pages_per_site <= 10:
        raise ValueError("max-pages-per-site must be between 1 and 10.")
    input_path = args.input or _latest_audit_zip(args.downloads)
    targets = _load_targets(input_path, max_targets=args.max_targets)
    outcomes: list[QualificationOutcome] = []
    with zipfile.ZipFile(input_path) as archive:
        for index, target in enumerate(targets, start=1):
            print(f"[Veridra] Qualifying {index}/{len(targets)}: {target.name}")
            findings = _audit_findings_for_target(archive, target)
            outcomes.append(
                qualify_target(
                    target,
                    max_pages=args.max_pages_per_site,
                    top_audit_findings=findings,
                )
            )
    generated_at = datetime.now(UTC).isoformat()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    args.output_directory.mkdir(parents=True, exist_ok=True)
    output_path = args.output_directory / f"VERIDRA_QUALIFICATION_{stamp}.zip"
    output_path.write_bytes(
        _build_archive(
            source_path=input_path,
            outcomes=outcomes,
            generated_at=generated_at,
            max_pages_per_site=args.max_pages_per_site,
        )
    )
    rows = [_aggregate(outcome) for outcome in outcomes]
    print(
        json.dumps(
            {
                "input": str(input_path),
                "output": str(output_path),
                "business_targets": len(outcomes),
                "ready_for_manual_qualification": sum(
                    1 for row in rows if row["review_state"] == "ready_for_manual_qualification"
                ),
                "needs_manual_review": sum(
                    1 for row in rows if row["review_state"] == "needs_manual_review"
                ),
                "persistence": "none",
                "outreach": "none",
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if outcomes else 2


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
