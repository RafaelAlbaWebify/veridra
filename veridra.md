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

## VERIFIED STATE / HANDOVER — 2026-10-16
- TRON synthetic full business lifecycle passed 14/14 checks (2026-10-16), including isolated restart/backup/restore. Combined public-site audit + synthetic workflow passed both stages in `VERIDRA_WEBIFY_ENGAGEMENT_REVIEW_20261016_165400.zip`; not a real client engagement.
- Basecamp public audit: 10 pages, 70 findings (45 pass/15 attention/10 unavailable), 11-page PDF; static `/books` unnamed-link warning not reproduced by sampled DOM heuristic, remains **disputed**, not a confirmed high-severity defect.
- Backup: 15/15 focused Windows tests PASS; C: disk 1 / D: disk 0, October 15 snapshot copied to D: with matching SHA-256; isolated D: restore recovered 85 files, SQLite `quick_check=ok`. Both SSDs are inside TRON; no whole-PC offsite protection. Do not upload backup bytes.
- Historical SaaS Stripe binding remains protected; **provider-side status unknown**. Do not delete or charge.
- CURRENT CI BLOCKER: latest completed run for `e86ac36` (run 38948634875) **FAILED strict mypy**: `tests/test_webify_engagement_review.py:61` missing parameter type annotation; Windows job PASS. Earlier syntax, Ruff and typing failures from repeated microcommits. Latest verified CI is **RED**, not green.
- NEXT TOMORROW: fix that mypy annotation and audit entire changed test for remaining lint/types; implement/use reproducible preflight equivalent to `tools/audit_operator_imports.py`, `ruff check .`, `mypy src tests`, targeted pytest. Batch fixes, verify local gate BEFORE pushing and then latest GitHub CI.
- AFTER GREEN CI: safe read-only check of legacy Stripe provider status; verify advanced recurring lifecycle + commercial report accuracy + human operator usability in consolidated acceptance; focused PR review, release/rollback readiness and request explicit merge permission. Do not repeat proven backup tests without a concrete reason.
- SHUTDOWN SAFE: No asynchronous work is running in this chat; TRON may be powered off. Resume via this file and GitHub checks.
