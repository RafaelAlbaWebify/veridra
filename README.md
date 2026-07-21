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
- server-side finding filters and dedicated Website health, Search visibility, AI discoverability, Trust signals, and Security posture views;
- JSON API plus printable HTML reports with metadata, prioritised actions, per-area summaries, full evidence, and recommendations;
- deterministic ZIP evidence packages containing JSON, HTML, and a SHA-256 manifest;
- explicit local assessment history with deterministic identifiers, atomic writes, comparisons, retention, and deletion controls;
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

## Local history

Veridra does not save assessments automatically. The operator must select **Save locally** for an assessment to be written to the local data directory. Saved data is limited to the existing assessment model; Veridra does not store credentials, cookies, form submissions, or request bodies.

Set `VERIDRA_DATA_DIR` to choose the parent data directory. When it is not set, Veridra uses `~/.veridra/history`.

## Safety boundary

Veridra is limited to bounded public evidence collection. It is not a penetration test, does not authenticate, does not submit forms, and must reject private or non-public targets before any website request. DNS posture checks are passive and do not connect to mail servers, transfer zones, enumerate subdomains, or guess DKIM selectors.

## Development status

Veridra 1.0.0 is a verified loopback-local product. Public deployment controls, multi-tenant operation, accounts, billing, external backlink providers, and sampled LLM visibility checks remain deferred until their operational and commercial requirements are justified.
