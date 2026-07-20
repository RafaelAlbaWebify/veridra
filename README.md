# Veridra

Automated website assessment for visibility, AI discoverability, trust signals, technical health, and public security posture.

## Current vertical slice

- deterministic demo assessment;
- evidence model and findings;
- checks for page structure, AI crawler readiness and public security headers;
- responsive operator dashboard;
- JSON demo API;
- deterministic repository audit;
- Ruff, strict mypy, pytest and GitHub Actions verification.

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

This repository is temporarily public during development and is intended to become private after completion.
