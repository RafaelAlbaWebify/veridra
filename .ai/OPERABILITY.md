# Operability Gates

## Current computed state
- Development usable: **PASS**
- Internal testing ready: **PASS**
- External beta/testing ready: **FAIL**
- Real prospect ready: **FAIL**
- Production ready: **FAIL**
- Weighted real-world operability: **33%**
- REAL OUTREACH COUNT: **0**

A project is never promoted by wording such as “looks ready”; every criterion below must pass with evidence.

## Gate 1 — Development usable — PASS
Criteria:
- package installs in supported dev environment;
- app/audit entrypoints exist;
- core tests run in CI;
- local browser workflow is available;
- no unresolved development-blocking P0.
Evidence: CI on `993b6f5...`.

## Gate 2 — Internal testing ready — PASS
Criteria:
- lint/type/unit suite green;
- deterministic audit green;
- browser audit green;
- synthetic commercial lifecycle green;
- Windows portability/operator Playwright green;
- persistence/restart/backup behavior covered synthetically.
Evidence: GitHub Actions run `33895989746` success.

## Gate 3 — External beta/testing ready — FAIL
Must all pass:
- hosted HTTPS environment exists;
- DNS/TLS/edge controls configured;
- durable storage mounted;
- web and worker supervised;
- real SMTP works on public origin;
- production preflight passes;
- deployment check passes;
- logging/backup/restore operational;
- no unresolved P0 affecting tester data/safety.
Current failure: deployment/provider evidence absent.

## Gate 4 — Real prospect ready — FAIL
Must all pass:
- Gate 3 passes;
- Stripe test-mode real provider lifecycle proven;
- accounting/invoice boundary exercised;
- Priority-A customer paperwork approved for use where required;
- activation/recurring/access/change/support/offboarding SOPs usable;
- complete actual-provider synthetic-customer dry run passes;
- no unresolved P0/P1 blocker in first-customer path;
- Rafael explicitly approves #284 after reviewing evidence.
Current failure: #296 open. **No real outreach permitted.**

## Gate 5 — Production ready — FAIL
Must all pass:
- real prospect gate technical/security/legal/provider criteria pass;
- exact release commit/config/evidence frozen;
- secrets managed outside source;
- backups scheduled and restore proven;
- observability/alerts adequate;
- Stripe/SMTP live-mode go-live decision verified;
- production operational runbook complete;
- human operator acceptance passes.

## Fully operative definition
100% means at least one real paying customer completes activation and at least one recurring service/payment cycle successfully, with reconciliation, monitoring/reporting, support/offboarding readiness, measured economics and no unresolved P0/P1 operational gap.