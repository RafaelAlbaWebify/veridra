# VERIDRA — Functional audit Batch 03: Prospect → Customer → Project

Date: 2026-10-17. Baseline: uploaded `VERIDRA_SOURCE_AUDIT.zip` (historical vs current GitHub). **9 additional modules; cumulative 26/243 = 10.70%**. No application code changed.

## Modules inspected and functional scope
| Module | ZIP LOC | Result |
|---|---:|---|
| `prospect.py` | 328 | Pydantic prospect identity, status, contact and workflow model; data contracts |
| `prospect_opportunity.py` | 125 | business scoring/triggers; provisional heuristics, not customer intent |
| `leadmap_import.py` | 105 | LEADS external schema validation and Prospect mapping |
| `customer_lifecycle.py` | 138 | lead/prospect conversion preserves agreement/billing states but error conflation |
| `tenant_customer_store.py` | 80 | tenant scope, specialized capability enforcement and customer save/load |
| `customer_store.py` | 336 | customer billing, agreement and onboarding validators; atomic file replacement |
| `agency_customer_web.py` | 271 | manual customer forms, work-start gate and billing evidence |
| `agency_customer_project_web.py` | 205 | gated project creation/link and attempted rollback |
| `agency_conversion_web.py` | 311 | alternative assessment-to-project flow (rejects operator-mode POST) |

## Findings (stable IDs; open until reproduced/reconciled)
- **F20 P1 — Customer file corruption treated as missing:** `customer_lifecycle.py:18–33`, `tenant_customer_store.py:48–63`. `_existing` suppresses any `TenantCustomerStoreError`, including malformed/unreadable existing file; conversion may overwrite it with a new customer record, losing commercial evidence. Distinguish not-found from invalid existing state.
- **F21 P1 — Corrupt customers invisible in lists:** `customer_store.py:317–327`. Each unreadable/invalid JSON is silently ignored by `list`; data remains on disk but disappears from UI. Surface repair warning.
- **F22 P1 — Concurrent customer edits silently overwrite:** `customer_store.py:259–336`. Unique temp file and fsync protect torn writes, not last-write-wins updates to agreement or billing by parallel requests. Add revision preconditions.
- **F23 P1 — Customer-project linking can leave orphan:** `agency_customer_project_web.py:160–193`. Project persisted first; customer update later; rollback delete exceptions silently swallowed. Record and reconcile partial outcomes. Extends earlier integrity concern.
- **F24 P2 — Candidate legacy conversion route:** `agency_conversion_web.py:185–225` refuses operator runtime; verify route in non-operator local-agency and historical use before deleting or simplifying.

Cross-links: F15 non-atomic prospect→activity→customer, F18 batch-import partial writes, F23 customer→project.

## Validation
**29 focused tests passed** across `test_customer_billing`, `test_customer_onboarding`, `test_customer_project_workbench_integration`, `test_agency_conversion_web`, `test_leadmap_import`, `test_prospect_opportunity`. Test showed Pydantic serializer warning for string vs HttpUrl in conversion test; not proof of production issue. No TRON acceptance, no error-injection tests yet.

Read each module source, reviewed branches/data validation/exception handling and traced cross-file interactions. Semantic review does not establish that every individual line ran; potential defect outcomes must be confirmed with dedicated scenarios before modification. Reconcile ZIP findings with current branch first.
