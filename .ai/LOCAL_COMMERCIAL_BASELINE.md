# Local commercial runtime baseline

Status: **REPOSITORY-VALIDATED**
Date: 2026-10-02

## Baseline

- head: `1da60641`
- GitHub Actions run: `37066657814`
- result: **success**

Passed:

- Ruff;
- strict mypy;
- full pytest;
- deterministic audit;
- prospect discovery acceptance;
- Windows portability;
- sales-contract Playwright acceptance;
- full operator Playwright acceptance.

## What this baseline proves

The commercial agency feature set can be composed as:

- `VERIDRA_ENV=production`;
- bind `127.0.0.1`;
- trusted origin `http://127.0.0.1:8011`;
- isolated commercial state under `%LOCALAPPDATA%\VeridraCommercial`;
- no VPS/cloud/PaaS application host;
- no public DNS/TLS/Caddy requirement;
- no SMTP requirement for local loopback startup;
- no Stripe requirement for free/local startup.

Local signup without SMTP preserves the normal request → verification → workspace creation model by exposing the verification continuation only inside the loopback `no-store` response. Remote/public production still requires SMTP.

Public/non-loopback production still requires HTTPS.

The supported local commercial launcher owns:

- web runtime;
- monitoring service;
- durable crawl worker service;
- quiesced backup/recovery tooling.

## What this does not prove

This is repository/CI evidence, not Rafael's actual workstation acceptance.

It does not prove:

- successful `VERIDRA_COMMERCIAL_OPEN.bat` execution on Rafael's PC;
- actual local commercial backup + independent second copy;
- Stripe test-mode lifecycle;
- real SMTP delivery;
- human UX acceptance of the commercial product.

Those remain H6/H7 evidence.

## Next

H6 uses Stripe test mode from the local runtime.

Stripe CLI can forward signed test events directly to:

`http://127.0.0.1:8011/api/billing/stripe/webhook`

No externally hosted VERIDRA endpoint is required.
