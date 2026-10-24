# VERIDRA — Operating Context (updated 2026-10-24)

## Mission and product boundary
- VERIDRA's current priority is the **private Webify operator** on Windows/TRON, **not a public SaaS launch**. Preserve prospect discovery/qualification, CRM, audits, evidence, reports, proposal drafts, onboarding, projects, remediation, monitoring, and customer billing workflows.
- Public SaaS signup, plans, subscriptions, public multi-tenancy and Stripe SaaS infrastructure are not active development goals. **Historical** SaaS/workspace/Stripe records remain protected; external provider status is UNKNOWN. Do not delete them or initiate charges.
- Repository: `RafaelAlbaWebify/veridra`; canonical branch after integration: `main`. Windows launcher: `scripts/windows/veridra-commercial-local.ps1`. Local operational data: `%LOCALAPPDATA%\VeridraCommercial`; untracked `infra/` may contain secrets and must remain untouched.

## What VERIDRA 22 was finishing
- The last user instruction in VERIDRA 22 was to **finish PR #399** before further functionality. At that point the handover described it as **open and not merged**, with local `refactor/webify-operator-only` five commits behind remote. That description was a historical snapshot, **not current status**.
- PR: https://github.com/RafaelAlbaWebify/veridra/pull/399 — `refactor/webify-operator-only`. Purpose: simplify to internal Webify operation; remove unnecessary SaaS-facing entry points and dependencies, improve architecture/modularity and reliability of prospecting, audits, sales and client workflows, without sacrificing operational data.
- The Engineering Harness is **development-quality infrastructure**, distinct from the PR's **product architecture changes**. Use it to validate changes; a green CI result is not real-world acceptance.

## Verified remote state (2026-10-24)
- PR **#399 MERGED/CLOSED** (GitHub API checked 2026-10-24). Prior assertion that it remained open is outdated.
- `main` at `cebedebc2ca9d0ca09850e82ea363e716da483c9`; merge/integration message: “Integrate operator-only refactor and engineering harness”.
- GitHub Actions runs on that exact main SHA: **CI SUCCESS** (run `40091216141`) and **SMB Real Validation SUCCESS** (run `40091216152`), both started 2026-10-24 11:46 UTC. This is **remote CI evidence**, NOT evidence of local TRON checkout, live application, current DB, or a genuine customer workflow.
- No open PRs were returned by GitHub API when checked. The former refactor branch still pointed at `699c04d4` (Oct 18); **do not assume the operator's local checkout follows main or is clean**.
- Historic `docs/operations/controlled-development-roadmap.md` still reports #399 unmerged and merge-gated phases at 0%; `.ai/CONTEXT.md` still describes a parallel SaaS commercial track. Treat these as **stale/conflicting until reconciled**; do not use their old percentages or SaaS direction as current truth.

## Real acceptance evidence and limitations (through 2026-10-18)
- Headed Google Maps live capture passed on TRON: two CLI queries (Vigo dentists 8/8 and hairdressers 8/8), plus GUI Find prospects → Collect visible results → Review (**20 captured / 20 selectable**). GUI ingest of real prospects was **not** exercised or authorized.
- `prospect_opportunity.website_evidence_kind` distinguishes owned site, third-party booking platform, external website and not-observed; absence of observed website is **not** proof of no site. Last test fixes were CI-validated, but new labels were not confirmed live on TRON.
- Synthetic full commercial lifecycle 14/14 passed (Oct 16), public Basecamp audit and printable PDF were exercised; neither proves an end-to-end real paying-client engagement. Backup isolated restore recovered 85 files with SQLite `quick_check=ok`; both SSDs on same machine, no offsite guarantee.
- Actual live outreach = **0** on available evidence. No sending, payment, live ingestion, destructive data modification, or provider actions without explicit approval.

## Next gate — continue from integrated main, not from the old PR
1. **Read-only TRON reconciliation:** inspect local branch/HEAD, working tree and remote tracking; preserve local changes and `infra/`; verify `main` integration is present locally before any update. Commands must be independent of current directory.
2. Inspect latest merged implementation, engineering Harness, required CI jobs and remaining acceptance obligations; reconcile the stale roadmap and `.ai/CONTEXT.md` explicitly rather than silently assuming all prior milestones completed.
3. Run one reproducible full local gate, preferably `scripts/windows/VERIDRA_DEV_PREFLIGHT.ps1 -Full` if still present/appropriate; separately test the real operator lifecycle on TRON where changed behavior warrants it.
4. Recheck the user-visible post-merge flow: prospect discovery / review and accurate website evidence → controlled CRM qualification → bounded audit → report → proposal **draft** → client delivery/monitoring (synthetic or read-only first). Record pass/fail/NOT RUN per gate.
5. Keep Stripe historical-record protection and backup/restore safety; any actual customer outreach, billing, ingestion, merge or destructive migration requires explicit approval. PR #399 is already merged, so do not attempt to merge it again.

## Mandatory engineering and communication rules
- Outcome-first, evidence-led work; "continue" means execute the next safe step. Inspect full failure set and adjacent affected surfaces, not only first error. Batch code + tests + documentation; do not use repeated speculative CI pushes.
- Before code pushes run compile/import audit, Ruff, strict mypy and relevant/full pytest via the repository's actual preflight. When only remote access is available, label **LOCAL PREFLIGHT NOT RUN**. Check all required Linux/Windows jobs on the final SHA.
- Distinguish: implemented vs unit-tested vs CI green vs live TRON accepted vs real customer validated. Avoid invented operability percentages. Read `docs/operations/controlled-development-roadmap.md` but first correct its historical merge status.
- Operator PowerShell commands must resolve `$HOME\Documents\GitHub\veridra` or their script root explicitly; never depend on the user's current directory. Never expose credentials, SQLite data or private archives.
- At each handover note SHA, branch, CI, local preflight, TRON evidence, blockers and exact next step. Do not promise asynchronous/background work.
