# Veridra

Automated website assessment for visibility, AI discoverability, trust signals, technical health, and public security posture.

## Current vertical slice

- bounded live public-website assessment with DNS/IP validation and pinned connections;
- redirect revalidation, response-size limits, and loopback-only operation;
- deterministic demo assessment for testing and review;
- evidence-backed findings for page structure, search readiness, AI crawler access, trust signals, and passive public security headers;
- homepage and `robots.txt` evidence collection without authentication or active scanning;
- responsive operator dashboard and JSON API;
- printable HTML reports with metadata, per-area summaries, prioritised findings, evidence, and recommendations;
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

Veridra is limited to bounded public evidence collection. It is not a penetration test, does not authenticate, does not submit forms, and must reject private or non-public targets before any network request.

## Development status

The verified local MVP is under active development. Public multi-tenant deployment, accounts, billing, external backlink providers, and sampled LLM visibility checks remain deferred until their operational and commercial requirements are justified.
