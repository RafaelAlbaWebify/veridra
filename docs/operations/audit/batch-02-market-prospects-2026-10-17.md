# VERIDRA — Functional audit Batch 02: Market Study and prospect persistence

Date: 2026-10-17. Baseline: uploaded `VERIDRA_SOURCE_AUDIT.zip`, not guaranteed to match latest branch head. Application changes: **none**.

## Coverage
10 new modules audited semantically (functions, conditionals, errors, persisted-state contracts and cross-component integration); **17/243 cumulative = 7.00%**. Batch 01: 7 modules; this batch: 10.

| Module | ZIP lines | Reviewed scope |
|---|---:|---|
| `agency_prospect_discovery_web.py` | 1438 | session routes, recovery and market/CRM transitions, review JSON, form validation |
| `agency_market_study.py` | 492 | study storage, query navigation, map rendering, HTML workbench |
| `market_intelligence.py` | 375 | models, queries, dedup, review hash, persistence |
| `tenant_prospect_store.py` | 162 | tenant isolation, prospect/activity/customer write ordering |
| `tenant_prospect_api.py` | 103 | capability-gated REST endpoints, error mappings |
| `prospect_ingest.py` | 118 | locking, identity merge, per-item import |
| `prospect_activity.py` | 118 | JSONL event append, fsync and creation idempotency |
| `agency_prospect_import_web.py` | 109 | imports, tenant authorization, origin policy, outcomes |
| `market_enumeration.py` | 104 | first-seen grouping and source coverage |
| `agency_prospect_discovery_evidence_web.py` | 228 | evidence ZIP, manifest, CSV, tenant scope |

## Findings (IDs stable; **OPEN / needs regression verification**)
- **F10 P1 — Archived review holds singleton:** `agency_prospect_discovery_web.py:159-271`. `_DiscoveryRegistry._require()` assigns recovered `manager=None` review to `_batch`; `start()` rejects any non-null `_batch`. Viewing an old review can prevent starting another live browser until explicit finish. Separate archived read from active slot.
- **F11 P1 — Review persistence error after collection:** `agency_prospect_discovery_web.py:215-242`. `_save_review` may fail after `observations` are available; unconditional `manager.stop` makes recovery depend on volatile singleton state. Define durable failure path.
- **F12 P2 — Corrupt study breaks market index:** `agency_market_study.py:28-39`; `all_studies` loads all JSON in a generator without isolating malformed files, aborting entire list.
- **F13 P2 — Repeated capture retains stale sector membership:** `market_intelligence.py:218-257`. `add_observations` merges observations but does not remove old associations when same sector is recaptured, while `captured` records latest size. Clarify historical-vs-current semantics.
- **F14 P1 — Concurrent Market Study write loss:** `market_intelligence.py:329-339`. `save` uses shared `.tmp` file and no lock/version check; parallel read-modify-writes may collide or overwrite.
- **F15 P1 — Non-atomic prospect/activity/customer update:** `tenant_prospect_store.py:45-52,72-152`. Prospect save/replace precedes event append and customer upsert. Later failure raises but does not reverse already committed changes.
- **F16 P2 — API misreports persistence failure as 404:** `tenant_prospect_api.py:74-88`. PUT catches any `TenantProspectStoreError`, even after partial write, returns 404.
- **F17 P1 — Ingest interprets any store load error as absent:** `prospect_ingest.py:85-118`. Broad `except TenantProspectStoreError` invokes save-new branch; restrict to explicit not-found.
- **F18 P1 — Batch ingest partial commit:** `prospect_ingest.py:85-118` and `agency_prospect_import_web.py:73-109`. Each item is saved individually; later failure leaves prior items stored, but user receives no per-item durable resume ledger.
- **F19 P2 — Event creation duplication race:** `prospect_activity.py:94-104`. Existence/size check followed by append has no cross-process serialization.

## Evidence, qualification and next steps
The ZIP's related ten pytest suites passed **48/48** with `PYTHONPATH=src python -m pytest -q --no-cov`: discovery web, review persistence, collection recovery, market study/intelligence, tenant prospect store, ingest, enumeration, import UI, market-to-CRM. They do not cover these failure-injection/concurrency edge cases. Findings are source-grounded risks requiring scenario proof and reconciliation against current GitHub branch **before** modifying application code.

Cross-component path: Discovery POST → registry + browser collection → saved review → Market Study observation merge + save → qualification/promotion → prospect store → activity log → customer upsert. Independent LEADS import path uses the same ingest/store layers. ZIP evidence export reads snapshot and remains tenant-scoped.

**Resumption:** Next batch should audit Prospect models, opportunity/qualification, manual CRM screens, customer conversion and persistence. Keep existing finding IDs; avoid calling static inventories line-by-line functional reviews. Do not modify commercial data or merge `main`.
