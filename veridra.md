# VERIDRA — Operating Context

## GUARDRAILS
- Respond in English, briefly and clearly; prioritize results, figures, file paths, and actions over filler. When the user's English could sound more natural to a native speaker, suggest a corrected version and explain the correction and why it is preferable in one short paragraph.
- At the start of a new chat, read this file from GitHub and check the branch, latest commit, and CI status before working.
- “Continue” means execute the next pending task, not merely propose it.
- Work autonomously: investigate, edit, test, and fix; ask only about risky decisions or essential missing information.
- Never claim something has been tested without evidence. Distinguish synthetic CI tests from real validation on TRON.
- Do not expose customer data, secrets, or SQLite databases in chats, reports, or commits.
- Do not delete historical data, activate real charges, or merge into main without explicit approval.
- After meaningful changes, update STATE with verifiable information and report the result, tests, and blockers. Always include the PR URL (https://github.com/RafaelAlbaWebify/veridra/pull/399) after commits so the user can monitor live yellow/green/red checks and report completion.
- Keep this file concise (target: 60 lines or fewer). Replace outdated state; do not accumulate a diary or duplicate documentation.
- Follow `docs/operations/controlled-development-roadmap.md`; on `EA`, report its fixed weighted phases exactly. Progress changes only after tests, green CI, and verified merge; do not confuse implementation with completion.

## PROJECT
- Goal: VERIDRA as Webify's private, local commercial tool on Windows/TRON, not a public SaaS product.
- Preserve CRM, prospecting, audits, reports, the commercial lifecycle, and customer billing.
- Repository: RafaelAlbaWebify/veridra. Work on `refactor/webify-operator-only`; draft PR #399; main remains untouched.
- Launcher: `scripts/windows/veridra-commercial-local.ps1`; actions: start/open/stop/status/preflight/backup/recovery-test/data-audit.
- Local data: `%LOCALAPPDATA%\VeridraCommercial`; backups and recovery tests must remain isolated.
- Legacy: retain identity/workspace structures and protection for historical Stripe bindings until compatibility is clarified; do not confuse these with Webify customer billing.

## STATE
- PR #399 on `refactor/webify-operator-only`; prior conflict resolved (merge `04ce312`); no merge to `main` authorized.
- TRON synthetic full lifecycle PASS on 2026-10-16: 14/14 checks, 17 steps; restart and isolated backup/restore. Evidence `VERIDRA_OPERATOR_E2E_ACCEPTANCE_20261016_122842.zip`.
- TRON multi-page live Basecamp audit: 10 pages / ~441 KB; 70 findings. Business applicability fix verified: 45 passed, 15 attention, 10 unavailable, no speculative LocalBusiness/hours/location actions. Evidence `VERIDRA_LIVE_AUDIT_REVIEW_20261016_152059.zip`.
- TRON accessibility/security follow-up `VERIDRA_LIVE_AUDIT_REVIEW_20261016_153543.zip`: sanitized element hints present; cross-origin newsletter form reclassified low, not an established vulnerability.
- CURRENT BATCH: accessibility parser recognizes wrapping labels and emits more useful sanitized references; compact print cover reduces blank-space/forced-page behavior; regression tests added for labels, hints, print CSS, and cross-origin review wording.
- Latest batch CI and TRON validation pending; do not infer new branch checks green from earlier CI.
- Historical Stripe SaaS binding exists in recovered old local data; external provider status UNKNOWN. Preserve record, do not charge or delete.
- Local `infra/` directory untracked: preserve. Actual commercial storage: `%LOCALAPPDATA%\\VeridraCommercial`; existing backups/recovery should stay isolated.
- TRON Basecamp PDF batch `VERIDRA_LIVE_AUDIT_REVIEW_20261016_160448.zip`: live 10-page audit passed; report reduced to 11 pages, but priority heading isolated at page end; accessibility hints remain static-only.
- CURRENT batch: report prioritization page break (`bd6f4f1`); misleading nth-of-type hints replaced with explicit document occurrences (`fa1309b`); live evidence runner now outputs a bounded 3-page DOM accessibility heuristic and quality-verdict JSON (`9695bae`). All require CI and TRON validation.
- TRON consolidated Basecamp run `VERIDRA_LIVE_AUDIT_REVIEW_20261016_162821.zip`: 10 pages, 45 passed / 15 attention / 10 unavailable; 3 browser DOM checks; priority pagination corrected, 11-page PDF; `/books` static unnamed-link warning not reproduced in sampled DOM heuristic.
- New batch `24c6342` adds per-page static-vs-DOM reconciliation to review ZIP; `251ac09` adds explicit static-heuristic and commercial applicability limitations to customer report; regression `24e66dc` added. CI/TRON verification pending.
- TRON Basecamp review `VERIDRA_LIVE_AUDIT_REVIEW_20261016_164507.zip`: technical PASS, static-vs-DOM reconciliation delivered; 5 unnamed-link warnings on `/books` not reproduced in sampled browser DOM, so remain disputed, not confirmed defects.
- New one-command `VERIDRA_WEBIFY_ENGAGEMENT_REVIEW.bat`: runs read-only live public audit followed by isolated synthetic full commercial lifecycle; bundles two separate evidence ZIPs + summary; does not contact prospects or activate payments. Added contract tests; CI/TRON evidence pending.
- NEXT: validate CI and execute single combined engagement on TRON; review audited website quality and synthetic operator funnel together, then independent backup and operator sign-off.
- AFTER: confirm independent second backup copy, human commercial acceptance and Stripe historical provider status safely; PR review and explicit approval required before merging.
- Do not declare full commercial readiness before real operator review and release sign-off.
