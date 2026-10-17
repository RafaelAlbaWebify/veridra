# VERIDRA functional audit — Batch 05: Projects, tasks and delivery
Source: user-uploaded `VERIDRA_SOURCE_AUDIT.zip` (may differ from latest branch). Date: 2026-10-17. **No application code changed.**

## Verified review scope
13 new modules, 2,298 lines: `project_store.py`, `tenant_project_store.py`, `project_delivery.py`, `tenant_project_delivery_store.py`, `task_store.py`, `tenant_task_store.py`, `tenant_project_api.py`, `tenant_task_api.py`, `agency_task_management_web.py`, `agency_project_customer_web.py`, `project_migration.py`, `project_ai_review.py`, `agency_project_index_web.py`. Reviewed function and error paths plus interfaces with client/project workflows. **Cumulative 47/243 = 19.34%; 196 remain.** Source semantic walkthrough, not branch coverage or execution of every line.

**56 focused tests passed** on the local ZIP snapshot (10 test files: project/task stores, APIs, management UI, delivery UI, migration, tenancy and index). These do not test all failure/concurrency scenarios.

## Stable findings: OPEN, reconcile against current GitHub before changes
- **F28 P1:** `task_store.py:69-75,119-128` task ID hashes the entire mutable record, so changing owner/status/notes changes ID; `tenant_task_api.py:88-107` PUT returns entity without new ID, causing stale external links. Fix requires stable identity/migration plan.
- **F29 P1 risk:** `task_store.py:130-134` deletes tasks with no referential checks; investigate evidence/child references before adding restrictions.
- **F30 P1:** `tenant_project_delivery_store.py:29-41` treats corrupt/unreadable delivery as nonexistence and returns new empty record; a later write can discard previous commercial evidence. Distinguish absent from invalid.
- **F31 P1:** `tenant_project_delivery_store.py:43-55` / `agency_project_customer_web.py:106-124` has no revision check; parallel updates can lose lifecycle events.
- **F32 P1 risk:** `project_delivery.py:127-175` allows `project_id` strings of length 24–64 only and joins value into filesystem path without the 24-hex validation found in `ProjectStore._path`. Validate ID at storage boundary; do not claim remote exploit without testing upstream.
- **F33 P1:** `project_store.py:189-224` silently omits malformed/unreadable project JSON in `list`, hiding records still referenced by customers.
- **F34 P2:** `project_store.py:149-177` derives initial ID from document hash, while `tenant_project_store.py:119-137` overwrites mutable content under same ID. A recalculated ID differs, potentially undermining migration/sync assumptions.
- **F35 P1:** `project_migration.py:96-158` can commit earlier projects then fail before producing complete evidence/journal; requires resumable transactional migration.
- **F36 P1:** `project_migration.py:160-192` rollback checks each checksum just before deletion; encountering a late changed target can leave earlier targets already deleted. Preflight all checksums before first destructive step.
- **F37 P2 risk:** `tenant_task_store.py:32-69` itself does not enforce referenced project exists; API POST checks it, other callers may not.
- **F38 P2 legacy candidate:** `tenant_project_api.py:58-86` still contains hosted-SaaS workspace plan checks. Verify runtime reachability and preservation requirements before deleting.

Positive controls: tenant scope/capabilities, Pydantic validation of delivery acceptance and task verified status, atomic-temp-and-fsync writes, source checksums and fingerprints during migration, AI review grounded in saved assessment findings.

**Do not mark any issue fixed based on this historical ZIP alone.** Implementation must reconcile to current branch, preserve customer/Stripe evidence, and batch identity/persistence changes coherently. Next modules: crawl/history/report/monitoring.
