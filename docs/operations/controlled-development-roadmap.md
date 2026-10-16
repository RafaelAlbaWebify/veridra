# VERIDRA — Controlled Development Roadmap

Baseline: 2026-10-16. Repository `RafaelAlbaWebify/veridra`; draft PR [#399](https://github.com/RafaelAlbaWebify/veridra/pull/399), base `main`; 148 changed files; last audited branch CI green. No merge evidenced for #399.

## Progress rules
- **Fixed weights** are effort/prioritization allocations, not estimates of already completed work. Each phase sums to 100%.
- Subphase completion is **binary, 0% or 100%**: 100% only after required implementation, automated tests, successful CI and merge into the target branch. Otherwise 0%, with implementation/CI/TRON evidence recorded as separate labels. No speculative intermediate percent.
- Phase progress = sum(weight × completion / 100). No global percentage: no fixed weighting across phases was agreed.
- Preserve numbering and weights. Add/redefine scope only through an explicit roadmap change with rationale; never silently rebase completion.
- **EA**: output every subphase with exact form `Phase N.M → Name → Brief description → X% complete → Weight: Y% of phase total.`, then `Total phase progress: Z%` computed by weighting. Clearly distinguish implemented, tested, CI pending, and merged in the description.
- Use small focused PRs for new work. PR #399 is an existing, substantial unmerged exception; split only if safe, not for cosmetic reasons.
- Evidence must be tied to commit, CI, actual TRON output, or merge status. Keep data and credentials out of GitHub.
- Do not merge into `main`, remove historical data, or enable real payments without explicit approval.

## Phase 1 — Private operator runtime (merge-gated: 0%)
- **1.1** (35%): Local-only startup and identity. Evidence: Windows launcher; loopback `/agency` HTTP 200 on TRON restored copy; no merge.
- **1.2** (35%): Disable SaaS entry points and quotas without losing business features. Evidence: TRON `/signup`, `/login`, `/plans`, `/billing`, `/workspace` HTTP 404; repository tests; no merge.
- **1.3** (30%): Consolidate code and regression safeguards. Evidence: import audit/tests; #399 unmerged.
- **Phase progress: 0%** (35×0 + 35×0 + 30×0).

## Phase 2 — Data safety and compatibility (merge-gated: 0%)
- **2.1** (40%): Consistent backup and isolated restore. Evidence: 85 files recovered on TRON; SQLite quick_check=ok; no merge.
- **2.2** (30%): Restored-data inventory and non-destructive application smoke. Evidence: 1 user, 1 tenant, 0 projects/assessments; restored `/agency` and `/health/live` HTTP 200; no merge.
- **2.3** (30%): Legacy subscription/workspace compatibility decision. Evidence: 1 legacy SaaS Stripe binding and 1 workspace config; disposition unresolved; no merge.
- **Phase progress: 0%**.

## Phase 3 — Business workflow acceptance (merge-gated: 0%)
- **3.1** (30%): Prospect discovery, qualification and sales/proposals. Evidence: code and automated tests present; complete real TRON workflow not yet evidenced.
- **3.2** (30%): Customer onboarding, projects, bounded audits and reporting. Evidence: code and Playwright coverage present; real full workflow not yet evidenced.
- **3.3** (25%): Remediation, monitoring and Presence Care/customer billing. Evidence: code and tests present; separate acceptance still required.
- **3.4** (15%): Windows operator usability and end-to-end acceptance. Evidence: restored-snapshot smoke passed, NOT full human/workstation acceptance.
- **Phase progress: 0%**.

## Phase 4 — Release and ongoing operations (merge-gated: 0%)
- **4.1** (30%): Windows restart/worker supervision and independent recovery evidence. Evidence: launcher and backup/recovery tests; independent secondary copy not evidenced.
- **4.2** (30%): Focused PR review and automated CI gates. Evidence: #399 CI green at baseline; large draft PR with 148 changed files remains unmerged.
- **4.3** (20%): Operator documentation, known limitations and rollback procedure. Evidence: local operating docs and `veridra.md` exist; release sign-off outstanding.
- **4.4** (20%): Explicit authorization and controlled integration to `main`. Evidence: no authorization, no merge.
- **Phase progress: 0%**.

## NEXT
1. Validate the latest CI and inspect the existing historical Stripe binding protection without exposing values.
2. Verify the remaining real TRON business flow, restart, and independent-copy requirements; document only observed evidence.
3. Review/split #399 if safe; request explicit authorization before a merge. Update merge-gated progress only on verified merges.
