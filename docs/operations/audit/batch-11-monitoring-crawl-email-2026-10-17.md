# VERIDRA functional audit — Batch 11: monitoring routes, SMTP, crawl profiles and CLIs

**Source baseline:** user-uploaded `VERIDRA_SOURCE_AUDIT.zip`, 2026-10-17; potentially behind GitHub. No application code, production data or customer communications changed.

## Scope and method

Nine additional modules (physical line counts from ZIP; **1,869 lines total**):

| Module | LOC | Contract and implementation reviewed |
|---|---:|---|
| `monitoring_web.py` | 280 | legacy root-level scheduling/email UI, manual crawl and retry |
| `agency_monitoring_web.py` | 315 | active agency route, capability and entitlement checks, saved assessment navigation |
| `tenant_monitoring_api.py` | 166 | project read/write, run dispatch, HTTP error mapping |
| `email_delivery.py` | 342 | SMTP transport, attempt store, content digest, failure recording |
| `crawl_profile_web.py` | 328 | crawl/HTML/PDF/export routes, usage reservations, project/profile access |
| `crawl_profiles.py` | 115 | hard caps, quick/standard/deep/custom limits |
| `monitoring_worker_cli.py` | 44 | CLI arguments and tenant-root environment |
| `crawl_worker_cli.py` | 40 | bounded one-shot job CLI and tenant-root environment |
| `crawl_worker_service.py` | 48 | polling loop, bounds validation and worker invocation |

Reviewed function bodies, branches, exception handling, inputs, writes and dependency relationships; traced which routers are actually included by `runtime.py`. Not every possible runtime path executed. Local ZIP check: **37 tests passed** across monitoring, agency monitoring, tenant monitoring, SMTP, crawl profiles and monitoring-job integration; Pydantic emitted a URL serializer warning in test fixtures.

**Cumulative 94/243 = 38.68% reviewed; 149 modules pending.**

## Findings — new IDs (all baseline-dependent)

**F70 [P1, confirmed on ZIP] — Legacy monitoring router not mounted.** `monitoring_web.py:24,93–280` defines root-level `/monitoring` endpoints; `runtime.py` includes `agency_monitoring_router` but has no `monitoring_web.router` import or include. Only `tests/test_monitoring_web.py` mounts it independently. Therefore these routes are not reachable through the normal runtime in the ZIP. This is a **legacy candidate**, not permission to delete its supporting stores, tests or historical data. Trace any alternate entrypoint and backups before removal.

**F71 [P1, confirmed contract risk] — Two monitoring execution paths have different delivery semantics.** `monitoring_web.py:143–178` directly performs assessment and catches email delivery failures without surfacing to the operator. Active `agency_monitoring_web.py:284–315` delegates to `tenant_monitoring_api.py:135–166` and `tenant_monitoring_execution.py`. Retaining the unmounted code raises maintenance/consistency cost. Establish one canonical implementation; record differences before deprecation.

**F72 [P1, ZIP design defect] — Email may send successfully before durable attempt is written.** `email_delivery.py:207–254`: `sender(active,message)` executes first; only afterwards `EmailAttemptStore.save()` records success/failure. If save fails, caller may retry an already accepted SMTP message. Linked to F52. Repair via durable pending attempt and idempotency semantics, with production-safe reconciliation.

**F73 [P2, ZIP] — SMTP status overclaims delivery.** `email_delivery.py:220–251` labels success `EmailStatus.delivered` after SMTP `send_message` returns. This proves SMTP server accepted the message, not recipient mailbox delivery. Linked to F56; consider `accepted_by_smtp` in UI with migration-safe compatibility.

**F74 [P1, design risk] — Crawl usage reservations can outlive failed crawls.** `crawl_profile_web.py:112–129` reserves audit and maximum page quota before `assess_url`; error path raises HTTP 400 without explicit release/reconcile in this function. Must inspect `reserve_tenant_usage` and policy store for self-expiry/rollback before asserting leaked quota. Follow across synchronous and worker routes.

**F75 [P2, actual duplicate execution risk] — Monitoring manual path bypasses durable worker.** `monitoring_web.py:164–178` runs `assess_url` and directly saves `HistoryStore`, while active agency route delegates through tenant-aware execution; the former is unmounted in standard runtime, therefore not an active security problem in that runtime. Confirm no other entrypoint exposes it.

**F76 [P2, review] — CLI one-shot limits not validated at command boundary.** `monitoring_worker_cli.py:10–40` and `crawl_worker_cli.py:10–36` accept arbitrary signed `--limit`, while `crawl_worker_service.py:22–46` explicitly restricts 1–100. Verify worker `run_once` safeguards and add consistent CLI rejection for `limit <= 0` / excessive values; do not claim a negative limit executes negative jobs.

**F77 [P2, ZIP] — Invalid stored SMTP attempt silently omitted.** `email_delivery.py:155–174` catches disk/parse errors per file and continues. Operator may see incomplete email history without an integrity warning. Avoid deleting evidence; report corrupted artifact count. Linked to F53.

## Positive controls and integration cautions

- `crawl_profiles.py` validates custom values against global caps, limits URLs per sitemap and applies resolved profile defaults. Do not delete it.
- `tenant_monitoring_api.py` requires tenant capabilities for GET/PUT/run and uses `TenantProjectStore` for isolation.
- SMTP enforces message byte limit, TLS configuration and sender/recipient model validation, and writes attempts atomically to a unique digest file.
- `agency_monitoring_web.py` escapes project labels and constrains schedule editing via tenant capability and plan checks.
- `crawl_profile_web.py` is excluded from the operator runtime but included outside operator mode; classify as **profile-dependent**, not dead.
- Worker CLI modules are external process entrypoints; a missing internal import reference is **not** evidence of dead code.

## Follow-up acceptance before fixes
Compare exact modules against latest remote branch, verify runtime route inventory for operator/local agency, inject write failure after fake SMTP acceptance, exercise quota release under failed crawl, and verify worker limit validation. Update finding statuses `confirmed_current`/`fixed_unverified`/`obsolete` with commit and test evidence. No live SMTP, quota reservation, customer data, or restoration exercised.
