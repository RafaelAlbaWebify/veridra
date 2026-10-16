# VERIDRA — Operating Context

## GUARDRAILS
- Respond in English, briefly and clearly; prioritize results, figures, file paths, and actions over filler. When the user's English could sound more natural to a native speaker, suggest a corrected version and explain the correction and why it is preferable in one short paragraph.
- At the start of a new chat, read this file from GitHub and check the branch, latest commit, and CI status before working.
- “Continue” means execute the next pending task, not merely propose it.
- Work autonomously: investigate, edit, test, and fix; ask only about risky decisions or essential missing information.
- Never claim something has been tested without evidence. Distinguish synthetic CI tests from real validation on TRON.
- Do not expose customer data, secrets, or SQLite databases in chats, reports, or commits.
- Do not delete historical data, activate real charges, or merge into main without explicit approval.
- After meaningful changes, update the STATE section with verifiable information and report only the result, tests, and blockers.
- Keep this file concise (target: 60 lines or fewer). Replace outdated state; do not accumulate a diary or duplicate documentation.

## PROJECT
- Goal: VERIDRA as Webify's private, local commercial tool on Windows/TRON, not a public SaaS product.
- Preserve CRM, prospecting, audits, reports, the commercial lifecycle, and customer billing.
- Repository: RafaelAlbaWebify/veridra. Work on `refactor/webify-operator-only`; draft PR #399; main remains untouched.
- Launcher: `scripts/windows/veridra-commercial-local.ps1`; actions: start/open/stop/status/preflight/backup/recovery-test/data-audit.
- Local data: `%LOCALAPPDATA%\VeridraCommercial`; backups and recovery tests must remain isolated.
- Legacy: retain identity/workspace structures and protection for historical Stripe bindings until compatibility is clarified; do not confuse these with Webify customer billing.

## STATE
- GitHub verified on 2026-10-16: commit `4368d045`; Linux and Windows CI completed successfully.
- TRON: backup and isolated recovery of 85 files succeeded; SQLite identity quick_check=ok.
- Restored inventory: 1 user, 1 tenant, 1 tenant directory, 0 projects, 0 assessments, 1 legacy workspace configuration, 1 legacy SaaS Stripe binding, 0 plan events; no warnings.
- New script `tools/webify_restored_runtime_smoke.py`: runs an ASGI smoke test on a temporary copy of the snapshot; NOT yet executed on TRON.
- Last known local TRON branch: `refactor/webify-operator-only`, commit `ad4efde`; untracked `infra/` directory: do not delete.
- NEXT: check the working tree, then update the local branch with `git pull --ff-only`; run the smoke test against `%LOCALAPPDATA%\VeridraCommercial\recovery-test-20261015_200939` and review the result.
- AFTER: verify the historical Stripe binding status without revealing secrets; decide on cleanup closure and acceptance of PR #399.
- Do not declare 100% real-world operability or merge into main until functional acceptance on TRON and explicit approval.
