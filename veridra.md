# VERIDRA — Operating Context

## GUARDRAILS
- English; concise, evidence-led answers. If useful, suggest a more natural phrasing of the user's English in one short paragraph.
- New chat/resume: read this file, roadmap, current branch/commit, PR and CI; recover context before editing.
- "Continue" means perform the next task, not merely propose it. Work autonomously; ask only for essential choices or risky authorization.
- Never claim a check passed without actual evidence; distinguish local tests, GitHub CI, synthetic TRON and genuine commercial use.
- Never disclose customer data, credentials, SQLite files or private backup archives. Do not delete historical records, activate billing/outreach or merge without explicit approval.
- Report roadmap completion using `docs/operations/controlled-development-roadmap.md`: binary merge-gated subphases; no speculative global percentage. On "EA" use exact prescribed weighted format.
- Keep this file under ~60 lines, updating state rather than accumulating daily notes. Include PR #399 link after commits.

## PROJECT
- Private Windows/TRON Webify commercial operator, **not SaaS**. Preserve CRM, prospecting, site audits, reports, proposals, onboarding, projects, remediation, monitoring and customer billing.
- Repo `RafaelAlbaWebify/veridra`; branch `refactor/webify-operator-only`; draft PR https://github.com/RafaelAlbaWebify/veridra/pull/399; `main` not authorized for merge.
- Launcher `scripts/windows/veridra-commercial-local.ps1` supports start/open/stop/status/preflight/backup/recovery-test/data-audit.
- Production data `%LOCALAPPDATA%\VeridraCommercial`; keep local untracked `infra/` untouched. Protect historical SaaS Stripe/workspace records until provider status is resolved.

## MANDATORY HIGH-EFFICIENCY ENGINEERING PROTOCOL (effective 2026-10-16)
1. **Outcome-first:** define one acceptance outcome and relevant failure modes; inspect related code, tests, CI configuration, prior failure logs and existing evidence before editing.
2. **Batch coherently:** implement code + regression tests + documentation together. Avoid microcommits, repeated evidence collection and expansion of scope without a blocker. Prefer focused PRs after #399.
3. **Pre-commit gate:** syntax/compile and import audit, `ruff check .`, `mypy src tests`, targeted `pytest -q --no-cov`, plus Windows-specific checks where relevant. Use the exact CI commands and versions from workflows, not guesses; create/use a single reproducible preflight command. If remote-only access prevents execution, explicitly mark preflight **NOT RUN**, inspect static formatting/types, and do not claim validation.
4. **Do not use CI as a debugger:** resolve known formatting, typing and test failures in one batch; push once after preflight, then verify the **latest head SHA's** full CI result. No "green" until all required jobs complete successfully.
5. **TRON once per milestone:** request a single consolidated command/evidence package only for changed functionality that requires Windows or real-world verification. Reuse earlier acceptance evidence for unchanged behavior.
6. **Close loop:** summarize committed SHA, preflight outcome, CI status, TRON evidence, blocker, next gate and PR link. Record outcomes, not interaction count or code volume. Never schedule background work implicitly.
7. **Guardrail for manual work:** minimize repeated commands; prefer safe read-only inspection and isolated synthetic tests; don't touch active data for recovery tests, don't send actual outreach or bill customers.
8. **Targets (aspirational):** >=90% first-push CI pass, <=1 avoidable CI rerun per batch, <=1 TRON run per milestone, near-zero unnecessary user actions; target ~4-6 remaining milestone QA cycles **conditional on defects**, not a promise.
9. **Stop rule:** after two preventable CI failures on a batch, halt feature work and do a complete gate-by-gate preflight before the next push. Correct the entire known failure class, not one symptom.
10. **Daily handover:** record last confirmed commit, failed/pending gate and error, exact next action, tests and safety constraints. On next session resume without re-running already verified work.

## VERIFIED STATE / HANDOVER — 2026-10-18
- Latest GitHub CI **SUCCESS**: commit `3cc99f2cdd6b` (run [39104659585](https://github.com/RafaelAlbaWebify/veridra/actions/runs/39104659585)), both Linux `verify` and Windows `windows-portability`. Review Intelligence sampling-safe now uses explicit immutable `ReviewCollectionPolicy`, not global module monkeypatching; CI regression tests cover isolation/callbacks. **TRON live Google Maps acceptance still NOT RUN**, no runtime speedup claimed.
- Development process defect: the refactor needed avoidable Ruff/mypy CI reruns because the existing `scripts/windows/VERIDRA_DEV_PREFLIGHT.ps1` was not executed before GitHub writes. The script already gates compileall, operator import audit, Ruff, strict mypy and selected/full tests. Require a recorded local `-Full` preflight **before** the next code push; when working only through remote GitHub connector, mark PRE-FLIGHT NOT RUN and avoid speculative microcommits.
- TRON synthetic full business lifecycle passed 14/14 checks (2026-10-16), including isolated restart/backup/restore. Combined public-site audit + synthetic workflow passed both stages in `VERIDRA_WEBIFY_ENGAGEMENT_REVIEW_20261016_165400.zip`; not a real client engagement.
- Basecamp public audit: 10 pages, 70 findings (45 pass/15 attention/10 unavailable), 11-page PDF; static `/books` unnamed-link warning not reproduced by sampled DOM heuristic, remains **disputed**, not a confirmed high-severity defect.
- Backup: 15/15 focused Windows tests PASS; C: disk 1 / D: disk 0, October 15 snapshot copied to D: with matching SHA-256; isolated D: restore recovered 85 files, SQLite `quick_check=ok`. Both SSDs are inside TRON; no whole-PC offsite protection. Do not upload backup bytes.
- Historical SaaS Stripe binding remains protected; **provider-side status unknown**. Do not delete or charge.
- Package 1 PASS (2026-10-17): TRON `VERIDRA_DEV_PREFLIGHT.ps1 -Full` passed compile/import audit (243 modules), Ruff, strict mypy (508 files), full pytest (100%) and deterministic audit. GitHub CI success for commit `017621e` (run 38997050436), both Linux `verify` and Windows `windows-portability`. Pytest warnings non-blocking.
- Package 2 IN PROGRESS (2026-10-17): Home low-contrast step labels FIX confirmed by operator. Find Prospects/Google Maps headed Chromium repeatedly exits during TRON isolated human acceptance: NOT OPERATIONALLY ACCEPTED. Root regression from overriding LOCALAPPDATA in isolated launcher; PLAYWRIGHT_BROWSERS_PATH corrected, Windows cache resolution reproduced in CI. Browser navigation failure handling, stderr diagnostics and stale discovery slot cleanup amended; TRON success STILL UNKNOWN. Latest branch commits include 1ac4847 (CI validation pending) and the isolation/regression fixes. Do not claim discovery fixed or ask for repeated TRON probes.
- Scope reviewed this turn: all 175 changed paths on draft PR #399 for change/risk inventory, detailed discovery process chain and launchers; full semantic review of all 243 source modules NOT complete. No ZIP clone available in model runtime; do not conflate passing Python test suite with a complete code audit.
- Priority: consolidate correctness and CI first, then obtain ONE read-only diagnostics bundle (existing Chromium stderr) rather than repeating browser launches; only then do focused TRON validation. Avoid microcommits and blind speculative patches.
- NEXT: verify new acceptance launcher on TRON, then personally exercise a synthetic commercial workflow including recurring monitoring, report inspection, navigation, restart and safe recordkeeping; evaluate historical Stripe status read-only separately. Reuse Basecamp and backup evidence.
- AFTER PACKAGE 2: one supervised real prospect pilot (public read-only audit + CRM qualification + proposal DRAFT only), followed by focused PR/release review and explicit authorization for any merge/outreach/payments.
- Pilot: after green CI and operator acceptance, prepare ONE real prospect read-only assessment/proposal draft; no actual outreach, payments, customer onboarding or main merge without explicit authorization.
