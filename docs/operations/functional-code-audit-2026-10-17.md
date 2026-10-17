# VERIDRA functional code audit — 2026-10-17 (in progress)

## Scope and truth standard
This is a **functional review backlog**, not a certification of all 243 modules.
Initial coverage: repository tree (243 Python modules, 267 test modules);
all 175 changed paths in PR #399 for migration/legacy impact;
read-through of the live Discovery request, registry, manager, browser-provider,
runner and Maps collection control flow. All 243 modules also received a
shallow pattern scan for suppressed errors, subprocess hazards and dynamic
execution; that scan is not equivalent to line-by-line semantic validation.

## Findings, based on actual code
1. **P0 / unresolved — headed browser startup is not acknowledged.**
   In `assisted_browser_provider.py`, `launch()` treats a child that has not
   immediately exited as a successful browser startup. In
   `assisted_browser_runner.py`, opening the persistent context and navigating
   to Maps happen asynchronously relative to this check. The waiting route
   in `agency_prospect_discovery_web.py` unconditionally presents
   `Browser opened`. There is no explicit child-to-parent ready message after
   `launch_persistent_context` / page setup. Therefore a browser that launches
   then exits can be reported as ready. **Do not claim fixed from CI.**
2. **P0 / unresolved — TRON Chromium closes during real discovery.**
   A verified Windows Playwright browser-cache regression was introduced by the
   isolated `LOCALAPPDATA` wrapper and is covered by Windows CI; the user still
   observes Chromium opening then closing. Therefore *cache path was a real
   defect but is not proven to explain the remaining closure*. Read the
   already-written local `discovery-browser-stderr.log` before further changes.
   Possible process-exit stages must be distinguished with evidence.
3. **P1 / corrected in branch — failed capture could retain singleton state.**
   `_DiscoveryRegistry.collect` left `self._batch` populated after
   collection failure, preventing a new `start`. Its exception path now
   releases the slot; regression test added. Confirm against merged/active
   runtime after successful CI.
4. **P1 / corrected in branch — broken pipe surfaced poorly.**
   Parent request channel can raise `BrokenPipeError` / `OSError` if child
   exits between process poll and write. Provider now maps this to a
   browser-unavailable diagnostic.
5. **P2 / review, not automatically change — hidden browser/DOM errors.**
   `assisted_google_maps.py` deliberately degrades some optional signal
   extraction and scroll failures by catching broad `Exception`. Verify that
   capture provenance distinguishes unsupported/selector-drift pages from
   missing optional metadata rather than pretending successful data coverage.
6. **P2 / review, not automatically change — rollback error silence.**
   `agency_customer_project_web.py` suppresses failure while deleting a
   newly created project after a customer-project linking error. This may
   conceal an orphaned project. Verify transaction consistency and record
   secondary rollback exceptions without revealing customer data.
7. **Architecture / legacy — PR #399 removes hosted SaaS routes, billing and
   related modules.** This removal is intentional for the private Webify
   operator but must be cross-checked against customer-facing billing,
   reporting and retained historical Stripe records. Do not resurrect SaaS
   behavior or modify customer data based solely on import or name matching.

## Review gates remaining
- Map the complete Webify workflow end to end (discovery -> qualification ->
  audit -> proposal -> customer -> project -> delivery -> recurring monitoring).
- Follow data writes and errors across SQLite, stores, authentication,
  migrations, backups and reporting.
- Inventory dead code and legacy through actual reachable call graph, not
  solely file names; distinguish intentional historical retention.
- Identify performance issues from measured hot paths and SQLite query
  patterns; do not propose optimization merely from intuition.
- Consolidate verified fixes with focused tests and full preflight. One
  TRON run per milestone; no further blind browser-launch attempts.

## Persisted audit batches and resumption protocol (2026-10-17)

- [Batch 01 — Discovery, seven modules and findings F01–F09](audit/batch-01-discovery-2026-10-17.md). Verified scope: **7/243 = 2.88%** of production Python modules received module-level semantic review on the uploaded ZIP snapshot. **236/243 remain pending**. A structural scan and PR diff inventory are NOT module-level functional verification.
- Status labels: **OPEN**, **RECONCILE REMOTE**, **FIXED VERIFIED**, **FIXED UNVERIFIED**, **NOT APPLICABLE**. Changes must be reconciled against the current remote branch before edits; ZIP line numbers refer to the uploaded snapshot.
- Future batches: create `docs/operations/audit/batch-NN-<flow>-YYYY-MM-DD.md` with exact module list, evidence, stable finding IDs, failure modes, tests, limitations, and cumulative coverage; update this index in the same commit. Do not overwrite previous evidence or inflate completion from automatic inventory.
- Follow-up fixes must point to finding IDs and carry source SHA, acceptance test evidence and operator proof where needed. Maintain a clear split between identifying bugs and modifying application behavior. Never modify production data or merge to main without explicit approval.

## Batch continuation — 2026-10-17
- [Batch 02 — Market Study and prospect persistence](audit/batch-02-market-prospects-2026-10-17.md): 10 additional modules, F10–F19. Local ZIP tests: 48 passed.
- [Batch 03 — Prospect → Customer → Project](audit/batch-03-customer-project-2026-10-17.md): 9 additional modules, F20–F24. Local ZIP tests: 29 passed.
- **Current module-by-module coverage: 26/243 = 10.70%; 217 remain.** The uploaded ZIP represents an earlier version than the current remote branch. Do not count prior structural inventories as individually completed reviews or mark findings fixed without current-head reconciliation.
- Local detailed appendices and coverage JSON remain in the ChatGPT audit deliverables for these batches; remote markdown files are durable handover summaries.

- [Batch 04 — Identity and runtime boundaries](audit/batch-04-identity-runtime-2026-10-17.md): 8 modules, F25–F27; 43 local focused tests passed.
- **Updated cumulative coverage: 34/243 = 13.99%; 209 production modules remain**. Percent tracks human-assisted semantic walkthrough of ZIP source only. It does not certify behavior of all lines or real TRON headed Chromium. Tests across batches 02–04: 120 passed.

- [Batch 05 — Project, task and delivery integrity](audit/batch-05-projects-tasks-delivery-2026-10-17.md): 13 modules / 2,298 source lines; stable findings F28–F38; 56 local ZIP tests passed. **Cumulative: 47/243 = 19.34%; 196 remain.** No app behavior modified. Compare ZIP vs remote SHA before fixes.

- [Batch 06 — History, crawl and monitoring execution](audit/batch-06-history-crawl-monitoring-2026-10-17.md): 6 additional modules / 934 lines; F39–F46; 21 local tests passed. **Cumulative audit: 53/243 = 21.81%, 190 modules pending**. ZIP source baseline; GitHub reconciliation required before fixing.

## Audit continuation: Batches 07–10 (2026-10-17)

| Batch | Modules | Cumulative | Findings |
|---|---:|---:|---|
| [07 — SQLite job engines and scheduling](audit/batch-07-jobs-schedulers-2026-10-17.md) | 8 | 61/243 (25.10%) | F47–F51 |
| [08 — Reports, PDF and delivery](audit/batch-08-reporting-2026-10-17.md) | 7 | 68/243 (27.98%) | F52–F56 |
| [09 — Proposals, deals, backups and schema](audit/batch-09-deals-backup-schema-2026-10-17.md) | 8 | 76/243 (31.28%) | F57–F62 |
| [10 — Sales workflow and commercial operations](audit/batch-10-sales-commercial-2026-10-17.md) | 9 | **85/243 (34.98%)** | F63–F69 |

**158 production Python modules remain unaudited functionally.** All batch findings refer to the user-uploaded ZIP snapshot; reconcile with current remote SHA before declaring defects current or making repairs. A 48-test local focused gate across job/report/backup test modules passed for batches 07–09; this is not a full CI run. No TRON acceptance, real SMTP, billing, retention deletion, or backup restore was executed. These source-level reviews are not proof of exhaustive control-flow/path coverage. No app source changed; only audit documentation was added.

## Audit continuation — Batches 11–12 (2026-10-17)
- [Batch 11 — Monitoring UI, SMTP, crawl profiles and worker entrypoints](audit/batch-11-monitoring-crawl-email-2026-10-17.md): nine additional modules, 37 focused tests passed, findings F70–F77. The independent `monitoring_web.py` router is not included in `runtime.py` (ZIP) and is a verified **legacy candidate**, not yet safe to delete.
- [Batch 12 — Lead, webhooks, assessment metering](audit/batch-12-lead-assessment-delivery-2026-10-17.md): nine additional modules, 28 focused tests passed, findings F78–F84. Focus: non-atomic lead/activity changes, webhook delivery journal, quota handling.
- **Accumulated semantic source review 103/243 = 42.39%; 140 production Python modules remain.** Coverage counts inspected source modules on ZIP, not exercised branches, not current-head verification. No code changes; user data remains untouched. Before fixes, inspect current SHA and merge duplication between finding IDs (e.g. F52/F72/F80) into shared transactions plan.

- [Batch 13 — Legacy authentication, sessions and throttles](audit/batch-13-auth-session-legacy-2026-10-17.md): eight additional modules, 994 source lines, 23 local ZIP tests passed, F85–F89. `runtime.py` excludes hosted login/session routes; preserve identity history until retention analysis.
- **Cumulative source-level semantic audit: 111/243 = 45.68%; 132 modules pending.** Batch 11: 37 tests; Batch 12: 28; Batch 13: 23. No live TRON verification or application modifications. Findings are tied to ZIP source, not automatically the newest GitHub head.

- [Batch 14 — Report profiles and stored AI/prospect review evidence](audit/batch-14-profiles-review-evidence-2026-10-17.md): eight source modules / 1,226 lines; 36 focused ZIP tests passed; F90–F96. **Cumulative 119/243 = 48.97%; 124 modules pending.** Particular concern: non-atomic hash-ID profile replace and project reference integrity. Findings pertain to uploaded ZIP until reconciled with GitHub HEAD.

## Coverage reconciliation + new batches — 2026-10-17

**Important denominator correction:** Rebuilt the unique module list from batches 01–14. The previous "119 modules reviewed" was a *sum of per-batch claims*, not a deduplicated count. The persisted batch module names have three repeated entries (`agency_crawl_profile_web.py`, `agency_report_profile_web.py`, `sqlite_session_manager.py`). **Verified unique baseline: 116/243**, not 119/243. All subsequent coverage counts use unique file paths and do not count reviews twice. Old percentages in earlier batch headers remain historical and should not be repeated.

- [Batch 15 — Identity persistence, offboarding and workspace locks](audit/batch-15-identity-policy-persistence-2026-10-17.md): 12 unique modules, 2,694 physical lines, F97–F104.
- [Batch 16 — Runtime composition, security headers and audit orchestration](audit/batch-16-runtime-audit-service-2026-10-17.md): 12 unique modules, 2,103 lines, F105–F112.
- Focused local ZIP gate: **43 tests passed** across workspace policy, offboarding, SQLite identity, preflight, security headers and runtime hardening. No live browser, external SMTP, offboarding, restore or customer writes.
- **New truthful cumulative coverage: 140/243 = 57.61% unique source modules; 103 remaining.** This percentage means inspected source and integration contracts, *not* exhaustive dynamic/path verification. Zip may differ from latest GitHub head. Never treat findings as current until reconciled.

- [Batch 17 — Observations, robots, opportunity, suppression and evidence](audit/batch-17-evidence-opportunity-2026-10-17.md): ten **unique** modules / 1,337 physical lines, F113–F118; 26 focused local ZIP tests passed.
- **Current reconciled unique-module coverage: 150/243 = 61.73%; 93 pending**. Earlier claimed batch sums overstated scope by three duplicate module names; see reconciliation above. This represents semantic source inspection on the uploaded ZIP and relevant cross-component dependencies, **not full branch testing nor verified live behavior**. No application code was changed, and no current-branch source comparison has been completed for these findings.

## Audit continuation — Batches 18–19 (2026-10-17)
- [Batch 18 — AI review, lead forms and scope changes](audit/batch-18-ai-review-forms-change-control-2026-10-17.md): 10 new modules, F119–F126; **32 focused tests passed** on the local ZIP. Main issues: non-atomic tenant binding for embedded forms, whole-deal lost updates, lack of reliable Chromium readiness acknowledgement in market CLI, evidence ZIP timestamp collisions.
- [Batch 19 — DNS, accessibility, content consistency, historical validation](audit/batch-19-analyzers-history-validation-2026-10-17.md): 10 new modules, F127–F133; **44 local tests passed**. Main issues: overinterpreted DNS/HTML signals, business-name validation collisions, legacy history retention route.
- **Unique modules semantically inspected: 170/243 = 69.96%; 73 remain.** The counts exclude the prior 3 duplicated names and mean source review rather than full dynamic branch execution. Findings refer to the user-uploaded ZIP and require reconciliation with current branch before application fixes. No live Maps/SMTP/webhook/restore test, no application changes and no merge to `main`.

## Audit continuation — batches 20–21 (2026-10-17)
- [Batch 20 — Recurring services, task interfaces, lead-form bindings](audit/batch-20-recurring-tasks-forms-2026-10-17.md): 8 unique modules, 1,564 source lines, findings F134–F141; 24 selected ZIP tests passed. Significant risk: corrupt existing Presence Care record silently converted into a new draft; unguarded concurrent plan/payment updates.
- [Batch 21 — Public capture, prospect CRM, adapters](audit/batch-21-public-capture-prospect-ui-2026-10-17.md): 8 unique modules, 2,474 source lines, F142–F149; 47 selected ZIP tests passed. Significant risk: assessment/usage/lead side effects are multiple non-atomic steps and prospect evidence can become disconnected after failure.
- **Current cumulative unique source review: 186/243 = 76.54%; 57 modules still pending.** Findings refer to the uploaded ZIP and require latest-branch reconciliation; selected green tests do not certify live browser/SMTP or all failure paths. No source code or commercial data modified.

- [Batch 22 — Retired hosted login/invitation routes](audit/batch-22-retired-account-invitation-2026-10-17.md): 8 unique modules / 1,400 source lines; F150–F154; 18 local ZIP tests passed. **Total now 194/243 = 79.84%, 49 modules pending**. Runtime excludes hosted auth routes; preserve migration/SQLite history. Findings apply to uploaded ZIP until current branch reconciliation. No application code changed.

## Source-module inventory complete: Batches 23–26 (2026-10-17)

- [Batch 23 — Core, crawl and Dublin acquisition](audit/batch-23-core-crawl-and-batch-cli-2026-10-17.md): 12 unique modules; F155–F160.
- [Batch 24 — GBP evidence, identity email and lead conversion](audit/batch-24-gbp-identity-and-conversion-2026-10-17.md): 12 unique modules; F161–F167.
- [Batch 25 — Legacy UI, readiness, evidence and preflight](audit/batch-25-legacy-ui-evidence-preflight-2026-10-17.md): 12 unique modules; F168–F174.
- [Batch 26 — Review intelligence and visual outreach](audit/batch-26-review-outreach-evidence-cli-2026-10-17.md): 13 unique modules; F175–F182.
- Local ZIP tests: **46 tests passed** across the selected suites for Batches 23–24, and **37 passed** across selected suites for Batches 25–26. The tests are synthetic and do not establish live browser reliability, outbound delivery, real acceptance, or fault tolerance.
- **Final deduplicated inventory: 243/243 direct `src/veridra/*.py` modules (100%)**, including `__init__.py` and `version.py`. Baseline counts were reconciled against all 243 filenames; 49 previously uncounted modules are included in these four batches.
- **Qualification: 100% module inventory/source-review batching ≠ full line-by-line correctness proof.** The 182 recorded F IDs mix real code defects, plausible edge-case risks, legacy/maintenance candidates and positive controls; many share root causes. There is no claim of 100% runtime branch coverage, per-line behavioral verification, or current GitHub-head equivalence. Next stages: (1) reconcile ZIP SHA with active branch file-by-file; (2) classify and deduplicate root causes; (3) targeted failure-injection and integration tests, then coherent implementation batches; (4) once-per-milestone TRON headed-Chromium acceptance.
- **Change boundary:** These 26 audit batches added documentation only. Do not merge to `main`, delete historical records, change real customer data, start outreach or make commercial deliveries based on the audit.

## Remediation tracking — active source of truth

**[CORRECTION_TRACKER.md](audit/CORRECTION_TRACKER.md)** is the master register for implementation status, source commits, CI/Windows/TRON acceptance and the grouped remediation backlog. Read it first when resuming work. The 243/243 source inventory is not a 100% bug-fix claim. Update the remediation tracker with each code-change batch; keep per-module audit findings as immutable evidence.
