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
