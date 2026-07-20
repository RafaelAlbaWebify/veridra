# Veridra

Automated website assessment for visibility, AI discoverability, trust signals, technical health, and public security posture.

## Current vertical slice

- bounded live public-website assessment with DNS/IP validation and pinned connections;
- redirect revalidation, response-size limits, and loopback-only operation;
- deterministic demo assessment for testing and review;
- evidence-backed findings for page structure, search readiness, AI crawler access, trust signals, and passive public security headers;
- homepage and `robots.txt` evidence collection without authentication or active scanning;
- bounded NS, MX, SPF, and DMARC posture checks with deterministic resolver fixtures;
- responsive operator dashboard with assessment-area summaries and a five-item priority-action queue;
- JSON API plus printable HTML reports with metadata, prioritised actions, per-area summaries, full evidence, and recommendations;
- deterministic ZIP evidence packages containing JSON, HTML, and a SHA-256 manifest;
- Ruff, strict mypy, pytest, deterministic repository audit, and Chromium browser acceptance checks in GitHub Actions;
- desktop and mobile screenshots plus machine-readable audit artifacts retained by CI.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m veridra.audit
.\.venv\Scripts\veridra-api.exe
```

Open `http://127.0.0.1:8000`.

## Safety boundary

Veridra is limited to bounded public evidence collection. It is not a penetration test, does not authenticate, does not submit forms, and must reject private or non-public targets before any website request. DNS posture checks are passive and do not connect to mail servers, transfer zones, enumerate subdomains, or guess DKIM selectors.

## Development status

The verified local MVP is under active development. Safe local history and comparisons, deployment controls, public multi-tenant operation, accounts, billing, external backlink providers, and sampled LLM visibility checks remain deferred until their operational and commercial requirements are justified.
