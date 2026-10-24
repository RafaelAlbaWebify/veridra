# VERIDRA functional audit — Batch 18: AI review, public lead-form UI and scope-change control

**Baseline:** uploaded `VERIDRA_SOURCE_AUDIT.zip`, dated 2026-10-17 and possibly behind the live GitHub branch. No application changes. **10 additional unique modules (2,473 physical source lines)**:

| Module | LOC | Reviewed focus |
|---|---:|---|
| `market_intelligence_cli.py` | 70 | market evidence input parsing, export entrypoint |
| `market_enumeration_cli.py` | 244 | bounded collection per query, failure isolation, manifest output |
| `market_opportunity_cli.py` | 367 | input files, evidence scoring, CSV and ranking export |
| `agency_ai_review_web.py` | 254 | bundle export/import, provenance validation, tenant-scoped save |
| `ai_review_exchange.py` | 290 | canonical hashes, schema, evidence reference and chronological validation |
| `agency_lead_web.py` | 342 | lead editing/deleting/conversion, HTTP responses, capability checks |
| `agency_lead_form_web.py` | 384 | embedded form create/edit/delete, tenant binding, rollback |
| `agency_change_request_web.py` | 177 | project scope change creation and state display |
| `agency_change_request_transition_web.py` | 154 | approval/decline lifecycle and evidence rules |
| `agency_progress_web.py` | 141 | chronological saved assessment comparisons |

Reviewed source function control flow, exception branches, response contracts, data writes and key dependencies. **32 local ZIP tests passed** across AI review, change request, lead form, progress and exchange schemas. These do not exercise real Maps Chromium, external leads, commercial data or injected filesystem failures. **Cumulative unique coverage 160/243 = 65.84%; 83 modules pending.**

## Findings (IDs continue F118; all require current-SHA reconciliation)

- **F119 / P1 — Lead-form deletion is not atomic across form and tenant binding.** `agency_lead_form_web.py:355–384` first deletes the form, then calls `binding_store.unbind`. If unbind fails, it recreates the form via `save`, which does not necessarily preserve its identity; the error path explicitly detects this. Implement durable coordinated operation/recovery with stable IDs; preserve tenant isolation.
- **F120 / P1 — Lead-form creation is non-atomic across its two stores.** `agency_lead_form_web.py:287–314` saves the form before establishing its tenant binding. Rollback may fail; an unbound form may remain. Existing rollback and warning are positive controls but do not guarantee atomicity. Failure-injection test should simulate second-store failures.
- **F121 / P1 — Scope-change updates overwrite concurrent changes.** `agency_change_request_web.py:138–177` and `agency_change_request_transition_web.py:85–154` each read a whole Deal, modify one nested `change_requests` tuple and save it. Distinct concurrent requests can erase each other's changes without a revision precondition. This shares root cause with F59; don't create separate incompatible locking schemes.
- **F122 / P2 — Scope-change sequence allocated by current tuple length.** `agency_change_request_web.py:150–177` chooses `sequence=len(deal.change_requests)+1`. Current code does not delete requests, so the value is stable in normal serial operation, but concurrency can allocate duplicate sequences. Resolve with F121.
- **F123 / P2 — AI result imported after validated integrity, but storage and UI are separate steps.** `agency_ai_review_web.py:183–221` validates schema/bundle hash/evidence and writes result. On store exception it redirects to a URL containing exception text; verify that user-safe errors avoid exposing internal file paths or unexpected state. No evidence of remote data leak established.
- **F124 / P2 — AI review bundle freshness depends on latest saved history.** `agency_ai_review_web.py:68–98` chooses `history.list()[0]` and loads it, assuming sorted newest-first and that latest file is readable; a damaged latest file causes a 404 despite older usable assessments. Distinguish recoverable history corruption from missing data, consistent with F39.
- **F125 / P2 — Market CLI uses per-query headed browser without readiness acknowledgement.** `market_enumeration_cli.py:61–127` invokes provider launch, sleeps an optional fixed duration, then collects. A fixed startup delay cannot prove the GUI is usable, so F01 applies to this entrypoint too. Do not add a second incompatible handshake.
- **F126 / P2 — Market output name has second-resolution collision.** `market_enumeration_cli.py:139–158` uses `datetime.now().strftime('%Y%m%d_%H%M%S')` for ZIP filename and opens archive in write mode; two same-second CLI runs to the same directory overwrite prior evidence. Use unique run identifier / no-clobber atomic output.

## Existing controls worth keeping
AI review import checks source bundle IDs/hashes, chronology, evidence references and typed schema before append-only save. Scope change schema requires a decision reference for approved/declined transitions. Lead edit endpoints enforce capabilities. Market enumeration preserves per-query failure rows instead of discarding partial successes, and does not mutate prospect state.

## Follow-up before editing
Compare these files against branch `refactor/webify-operator-only` HEAD. Exercise concurrent Deal update, lead-form binding rollback, two same-second enumeration invocations and AI-import error messaging in isolated fixtures. Treat prior CLI code and local forms as possibly profile-conditional; no deletion merely on lack of primary runtime import.
