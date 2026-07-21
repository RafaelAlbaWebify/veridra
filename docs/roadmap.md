# Veridra delivery roadmap

## Completed

- Repository-backed tested baseline.
- Bounded public-target collector with DNS/IP validation and pinned connections.
- Redirect revalidation, response limits, and loopback-only API.
- Live dashboard workflow and printable HTML report.
- Assessment metadata, deterministic prioritisation, and per-area summaries.
- Expanded robots.txt interpretation and passive discoverability/trust signals.
- Bounded NS, MX, SPF, and DMARC posture checks with deterministic DNS fixtures.
- Dashboard and printable-report priority-action sections.
- Server-side finding filters and dedicated assessment-area views.
- Deterministic ZIP evidence packages with JSON, HTML, and SHA-256 manifest.
- Explicit local assessment history with deterministic identifiers and atomic writes.
- Local comparison of added, resolved, changed, and unchanged findings.
- Local retention and explicit deletion controls.
- GitHub Actions verification with preserved diagnostic artifacts.
- Chromium desktop/mobile visual and accessibility acceptance checks.
- Verified loopback-local 1.0.0 milestone.

## Next

1. Define deployment controls: rate limiting, bounded concurrency, job isolation, abuse monitoring, and retention.
2. Complete local Windows acceptance testing and operator workflow review.
3. Prepare a controlled private-deployment milestone only after local acceptance evidence is complete.
4. Add optional provider interfaces for backlinks and sampled AI visibility only after commercial validation.
5. Define release packaging and upgrade behavior for non-developer operators.

## Deferred until justified

- Accounts and billing.
- Multi-tenant public deployment.
- PDF generation service.
- LLM API prompt sampling.
- Backlink data provider costs.
- Active vulnerability assessment.
