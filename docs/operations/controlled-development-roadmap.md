# VERIDRA — Controlled Development Roadmap (reconciled 2026-10-24)

## Baseline and evidence
Repository `RafaelAlbaWebify/veridra`. [PR #399](https://github.com/RafaelAlbaWebify/veridra/pull/399) is **MERGED**, not open. Main integration commit `cebedebc2ca9d0ca09850e82ea363e716da483c9`; GitHub CI and SMB Real Validation succeeded on that SHA. Later context-only commits are not substitutes for local TRON acceptance.

## Progress semantics
- Preserve historical phase numbering and weights; these are planning weights, **not guessed operational readiness**.
- Mark each subphase DONE only when its own implementation, tests, CI, merge, and specified TRON/operator acceptance gates have actually been evidenced. Integration #399 clears the **merge condition**, not all acceptance conditions.
- Use `DONE / PENDING TRON / PENDING EXTERNAL / PARTIAL`; only DONE contributes binary 100% to weighted progress. No global product percentage.
- On request `EA`, produce every subphase in the established weighted format with explicit denominator and gate evidence; don't silently recompute old phase percentages with changed definitions.
- Never ship outreach/payment or write live CRM data without explicit permission. Historical provider records are protected.

## Phase 1 — Private operator runtime
- **1.1 (35%)** Local-only startup/identity: implemented, formerly TRON loopback smoke accepted on restored copy; **PENDING post-merge TRON startup/restart**.
- **1.2 (35%)** SaaS entry points disabled without losing business features: former TRON 404 and repository tests; **PENDING post-merge operator route smoke**.
- **1.3 (30%)** Consolidated operator-only architecture/regression safeguards: PR #399 **MERGED**, CI passed for integration SHA; **DONE for merge/code gate**, pending local operational acceptance in 1.1/1.2.
- **Evidence-gated progress: 30%** (only 1.3 DONE).

## Phase 2 — Data safety and compatibility
- **2.1 (40%)** Backup/isolated restore: historical TRON 85-file recovery and SQLite check OK; **PENDING fresh post-merge backup/recovery evidence**.
- **2.2 (30%)** Non-destructive restored-state inspection: prior 1 user/1 tenant, loopback service smoke; **PENDING post-merge read-only inventory/smoke**.
- **2.3 (30%)** Legacy subscription/workspace compatibility: code prevents unsafe deletion; **PENDING EXTERNAL** provider status / controlled decision; do not erase old bindings.
- **Evidence-gated progress: 0%**.

## Phase 3 — Business workflow acceptance
- **3.1 (30%)** Discovery/qualification/proposals: live headed Maps (CLI 8+8, GUI 20) previously accepted, but no full post-merge qualification and draft; **PARTIAL**.
- **3.2 (30%)** Onboarding/projects/audit/report: automated tests and synthetic workflow, no full post-merge real-client evidence; **PENDING TRON**.
- **3.3 (25%)** Remediation/monitoring/Presence Care/client billing: implementation/test history, no complete post-merge acceptance; **PENDING TRON**.
- **3.4 (15%)** End-to-end operator Windows UX: historical capture-to-review and restored smoke only; **PENDING post-merge human E2E**.
- **Evidence-gated progress: 0%**.

## Phase 4 — Release and ongoing operations
- **4.1 (30%)** Restart/supervision/independent recovery: backup restore evidenced historically; both local SSDs in same PC, no independent off-host copy; **PENDING**.
- **4.2 (30%)** Full PR review and automated integration gates: #399 merged and CI passed on integrated SHA; detailed full 243-module semantic review not evidenced. **PARTIAL**.
- **4.3 (20%)** Operator docs/limitations/rollback: updated bootstrap context, acceptance/release signoff pending; **PARTIAL**.
- **4.4 (20%)** Controlled #399 integration to main: **DONE** (merged 2026-10-24); no implied approval for future PRs, payments or outreach.
- **Evidence-gated progress: 20%**.

## Immediate execution order
1. Inspect local TRON branch/HEAD/status safely; protect untracked `infra/`, data under `%LOCALAPPDATA%\VeridraCommercial` and historical Stripe/workspace references; avoid destructive pull/reset.
2. Run `scripts/windows/VERIDRA_DEV_PREFLIGHT.ps1 -Full` after safe synchronization; capture results per gate; local preflight **NOT RUN from remote GitHub-only access**.
3. Check actual loopback operator routes, headed prospect discovery/review including honest booking-platform classification, controlled synthetic CRM ingest, audit/PDF, proposal draft, project/monitoring, restart and isolated restore.
4. Record observed outcomes and artifacts; revise only the specific DONE gate justified by new evidence. Do not mistake SMB Real Validation CI for live TRON.
5. Keep historical Stripe provider state separate; no provider mutation or deletion based on repository tests.
