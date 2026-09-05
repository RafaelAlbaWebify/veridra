# Operability Gates

## Current computed state
- Development usable: **PASS**
- Internal testing ready: **PASS**
- External beta/testing ready: **FAIL**
- Real prospect ready: **FAIL**
- Production ready: **FAIL**
- Weighted real-world operability: **36%**
- Remaining to full operability: **64%**
- M1 business readiness: **~80%**
- REAL OUTREACH COUNT: **0**

Previous weighted operability was 33%. The increase to 36% is credited only to completed M1 operating controls: the standard monthly report, additional-work quotation, complaint/issue record and renewal/service-change record are now created and registered. No production/provider/customer stage receives credit from this change.

A project is never promoted by wording such as “looks ready”; every criterion below must pass with evidence.

## Gate 1 — Development usable — PASS
Criteria:
- package installs in supported dev environment;
- app/audit entrypoints exist;
- core tests run in CI;
- local browser workflow is available;
- no unresolved development-blocking P0.
Evidence: successful application CI on `993b6f5...`; subsequent AI-control migration changed documentation/tooling but introduced no application feature change.

## Gate 2 — Internal testing ready — PASS
Criteria:
- lint/type/unit suite green on the last fully verified application baseline;
- deterministic audit green;
- browser audit green;
- synthetic commercial lifecycle green;
- Windows portability/operator Playwright green;
- persistence/restart/backup behavior covered synthetically.
Evidence: GitHub Actions run `33895989746` success on `993b6f5...`.

Control-layer note: migration CI run `33943810013` failed only at Ruff in the new `tools/build_ai_context.py`; Windows portability and operator E2E passed. The Ruff defects were corrected in commit `d6b4d187...`; full CI revalidation is pending and must be recorded in `TEST_STATUS.json` when complete.

## M1 — Business-ready operating layer — ACTIVE (~80%)
Credited evidence:
- Presence Care scope/commercial model frozen internally;
- activation + recurring SOP frozen internally;
- payment/invoicing/suspension operating policy;
- access/secret-handling checklist;
- production change/backup/rollback checklist;
- proposal/quote structure;
- baseline assessment/evidence record;
- remediation approval + completion/acceptance records;
- subprocessor register architecture;
- customer lifecycle message pack;
- offboarding/access-revocation control;
- support/escalation SOP;
- monthly Presence Care report;
- additional-work quotation;
- complaint/issue handling record;
- renewal/upgrade/service-change record.

Remaining before M1 can pass:
- customer-facing MSA/Order Form/DPA/access authorization/SOW controls production-approved where required;
- first-market tax/invoice treatment recorded;
- final production provider/subprocessor posture known;
- jurisdiction/transfer/sector decisions completed where applicable;
- clean approved customer-facing versions released under the document register gate.

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
