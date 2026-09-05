# Operability Gates

## Current computed state
- Development usable: **PASS**
- Internal testing ready: **PASS**
- External beta/testing ready: **FAIL**
- Real prospect ready: **FAIL**
- Production ready: **FAIL**
- Weighted real-world operability: **38%**
- Remaining to full operability: **62%**
- M1 business readiness: **~90%**
- M2 deployment tooling: **IMPLEMENTED, NOT DEPLOYED**
- REAL OUTREACH COUNT: **0**

Operability history:
- 33% → 36%: recurring/reporting/exception operating controls completed.
- 36% → 37%: Access Authorization and SOW/Change Order business-reconciled.
- 37% → 38%: Ireland first-market tax/invoice operating reference completed.

M2 implementation after 38% does **not** increase operability yet. The canonical `deployment/` bundle, no-overlap worker supervision and quiesced backup automation remove engineering uncertainty, but DEPLOYED/EXTERNALLY VERIFIED credit requires a real host and evidence.

## Gate 1 — Development usable — PASS
Repository/package/application entrypoints exist and the last fully verified repository baseline is green.

## Gate 2 — Internal testing ready — PASS
Latest fully verified evidence: commit `060e2e6a8270ef71551d714b576a40413630bbfc`, GitHub Actions run `33944754836`, success across Linux Ruff/mypy/pytest/audit/browser/discovery/commercial acceptance and Windows portability/sales-contract/operator Playwright.

## M1 — Business-ready operating layer — ACTIVE (~90%)
Operating scope, activation/recurring SOP, payment/access/change/reporting/support/offboarding and Ireland tax/invoice reference are defined. Remaining blockers are production legal approval where required, actual transaction tax treatment, final production subprocessors/providers and applicable jurisdiction/sector decisions.

## M2 — Production infrastructure — ACTIVE, external evidence absent
Implemented repository evidence:
- canonical provider-neutral `deployment/` Compose/Caddy bundle;
- single-writer shared durable-volume topology;
- app port remains private behind Caddy;
- token/IP-redacted proxy logging baseline;
- bounded worker service and no-overlap timer;
- application backup script that stops the worker timer/service and web before asserting `--confirm-quiesced`;
- existing verified `veridra-backup` CLI used rather than a second backup format;
- backup service/timer and failure-safe web/worker restart;
- tests enforce the deployment/supervision/backup bundle;
- duplicate deployment implementation removed.

No M2 operability credit is granted until evidence proves:
1. a real EU host exists;
2. provider firewall is active;
3. public DNS/TLS work;
4. durable state survives container replacement;
5. systemd worker timer executes successfully without overlap;
6. a real scheduled backup archive is produced;
7. the archive is copied to independent off-host storage;
8. an isolated restore succeeds and `/health/ready` plus representative commercial state validate.

## Gate 3 — External beta/testing ready — FAIL
Must also have real SMTP on the public origin, production preflight/deployment checks, operational health/logging and no unresolved P0 affecting tester data/safety.

## Gate 4 — Real prospect ready — FAIL
Requires Gate 3, real Stripe test-mode lifecycle, accounting/invoice exercise, usable/approved Priority-A paperwork, complete actual-provider dry run, no first-customer P0/P1 and Rafael's explicit #284 approval. **No real outreach permitted.**

## Gate 5 — Production ready — FAIL
Requires exact release/config/evidence freeze, secret management, verified backups/restore, observability, Stripe/SMTP go-live decisions, runbook and human operator acceptance.

## Fully operative definition
100% means at least one real paying customer completes activation and at least one recurring service/payment cycle successfully, with reconciliation, monitoring/reporting, support/offboarding readiness, measured economics and no unresolved P0/P1 operational gap.
