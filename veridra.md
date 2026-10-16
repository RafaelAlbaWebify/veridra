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
- CI: `64ff49d` passed Linux + Windows, including synthetic full business lifecycle Playwright; later documentation changes require fresh CI.
- TRON: backup and isolated recovery of 85 files succeeded; SQLite identity quick_check=ok.
- Restored inventory: 1 user, 1 tenant, 1 tenant directory, 0 projects, 0 assessments, 1 legacy workspace configuration, 1 legacy SaaS Stripe binding, 0 plan events; no warnings.
- TRON restored-snapshot ASGI smoke PASS: `/agency` and `/health/live` = 200; public SaaS routes = 404; source data untouched.
- Last verified TRON local branch: `refactor/webify-operator-only`, commit `641f470`; untracked `infra/` directory: do not delete.
- Legacy Stripe audit: `tenant_offboarding.py` blocks deletion when historical subscription binding exists; regression test covers guard. External provider status UNKNOWN; preserve binding.
- TRON acceptance guide corrected: launcher uses positional commands; actual passed/remaining evidence documented.
- TRON E2E rerun 2026-10-16 FAILED at Save commercial progress: click completed, navigation exceeded Playwright 30s; prospect created/qualified, launcher startup/stop PASS. Evidence: `VERIDRA_OPERATOR_E2E_ACCEPTANCE_20261016_122222.zip` (local only).
- Proposal and commercial-progress waits now bound at 120s on branch; root cause of slow responses unresolved; CI and TRON rerun pending.
- NEXT: verify CI for new test wait, rerun `VERIDRA_OPERATOR_E2E_ACCEPTANCE.bat` on TRON; diagnose backend latency if operations again exceed 30s.
- AFTER: check independent backup/restart evidence and Stripe provider status safely, then review PR #399 for approval (no merge without consent).
- Do not declare 100% real-world operability or merge into main until functional acceptance on TRON and explicit approval.
