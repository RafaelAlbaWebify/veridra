# VERIDRA — cross-batch remediation map (post source-inventory)

Baseline: 26 audit batches from the user-uploaded source ZIP; 243/243 unique Python modules listed, source-level review completed by groups. **Do not interpret this as 100% functional correctness or runtime-path coverage.** All line refs in individual batch files are ZIP-based until reconciled with latest branch. No fixes authorized here.

## Root-cause clusters (deduplicate findings before tickets)
| Priority | Shared root cause | Related finding IDs | Proposed acceptance |
|---|---|---|---|
| P0 | Chromium launch not acknowledged, child exit misclassified, manager state incomplete | F01, F04, F05, F125, F109 | Parent receives bounded `ready` or typed `error` from child; real Chromium on TRON stays open through Maps collection; one operator verification after synthetic CI |
| P1 | Multi-file/store commercial mutations not atomic or resumable | F15, F18, F20, F23, F28, F31, F35, F36, F57, F64, F78, F79, F90, F119, F120, F121, F142, F143, F145, F155, F161, F168 | Idempotent operation ID, durable phases, detectable partial failures, repair workflow; fault-injection tests |
| P1 | Corrupted persisted records interpreted as missing or silently omitted | F12, F17, F20, F21, F30, F33, F39, F53, F58, F77, F83, F92, F140, F144, F149, F164 | Distinct not-found/corrupt/IO statuses and operator integrity warnings; preserve all raw records |
| P1 | External side effect precedes ledger/attempt write | F41, F45, F52, F56, F72, F73, F80, F81, F163, F169 | Pending/sending/accepted/failure journal, idempotent retry key; distinguish SMTP accepted from delivered |
| P1 | Missing CAS revision and cross-process serialization | F14, F22, F31, F42, F59, F97, F98, F100, F121, F135 | Check-and-set revision or transaction; concurrent stress + recovery tests; verify lease owner before deleting lock |
| P1 | Canonical ID and reference integrity | F08, F28, F34, F40, F43, F46, F91, F93, F115, F132, F148 | Stable identities across edits, reference guard before delete, explicit ambiguous identity matches |
| P1 | Browser/network safety inconsistencies | F06, F07, F09, F166, F171, F176, F179 | URL canonicalisation, bounded IPC and time budget, pinned safe HTTP connection (where relevant), no private target escapes |
| P2 | Legacy SaaS/router duplicates and outdated runtime wiring | F24, F38, F63, F70, F71, F75, F84, F85, F87, F106, F110, F141, F150, F151, F157, F172, F181 | Runtime route inventory in each supported mode + external CLI reference graph; preserve identity/billing history |
| P2 | Incomplete provenance and heuristics overstated | F55, F56, F74, F96, F111, F117, F118, F123, F127, F128, F129, F132, F165, F177, F180 | Evidence status enum, user-visible quality/limitations, source hashes and acceptance snapshots |
| P2 | Output artifacts / acquisition reproducibility and collision | F126, F158, F159, F167, F173, F175, F182 | Unique immutable run IDs, staging directory, input hashes, atomic ZIP publication |
| P2 | Expensive duplicated browser/HTML extraction paths | F07, F95, F160, F174, F178, F179 | Benchmark/contract fixture first; choose one shared primitive, preserve historical output schemas |

## Release order
1. Current-branch reconciliation and read-only existing TRON stderr evidence; **do not modify data or repeatedly launch Chrome as a diagnostic**.
2. Repair Chromium process readiness + recovery as one change with tests, after verifying all involved runner/provider/registry call sites.
3. Record-not-found vs-corrupt errors and repair-safe list visibility.
4. Centralized idempotency/revision/lease strategy, then business workflows (lead→project, deal→customer, reports/delivery).
5. Profile/legacy retirement only after route-graph, backup retention and migration plan.
6. Cross-version unit/integration/Windows CI, plus one supervised operator run per finished milestone.

## Audit evidence limits
- Completion denominator is direct `src/veridra/*.py` only; not PowerShell scripts, test files, infrastructure, JS templates or historical git refs.
- The 182 IDs are **not 182 proven active bugs**; many are risk hypotheses, duplicate symptoms and positive controls.
- Current branch includes post-ZIP application fixes. Every ID must be assigned `current` / `fixed_unverified` / `obsolete` with source SHA and failure test.
- No deletion of historical Stripe/tenant material, production merges, outreach or billing without operator approval.
