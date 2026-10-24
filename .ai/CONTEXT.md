# VERIDRA — AI Bootstrap Context (2026-10-24)

## Current direction
VERIDRA is the **private Windows/loopback operator for Webify**. The former multi-tenant commercial SaaS track is historical/deferred, **not the current development mandate**. Users purchase Webify services, not VERIDRA subscriptions. Preserve prospecting, opportunity qualification, customer CRM, bounded public audits, evidence, report/PDF, proposal drafts, onboarding, projects, remediation, periodic monitoring and Presence Care.

## Canonical integration
- Repository: `RafaelAlbaWebify/veridra`; current target `main`.
- PR [#399](https://github.com/RafaelAlbaWebify/veridra/pull/399) `refactor/webify-operator-only` **merged 2026-10-24**, incorporating operator-only simplification; integration commit `cebedebc2ca9d0ca09850e82ea363e716da483c9`.
- Engineering Harness integrated with the refactor; CI and SMB Real Validation both succeeded for that integration SHA. CI is **not** proof of installed TRON behavior or real customer acceptance.
- The historical `VERIDRA_ENV=production` and SaaS components in older documents are *legacy implementation/history*, not evidence they should be restarted. Never delete legacy Stripe/workspace data until external status is established and deletion approved.

## Evidence discipline
`public observation → verifiable evidence → affected surface → business impact → proposed fix → task → rescan`.
Bounded website/SEO, accessibility heuristics, AI crawler signals and passive security cannot be called penetration testing, complete SEO intelligence, accessibility certification, or guaranteed AI visibility.
Track separately: implemented, tested, CI-green, live-TRON accepted, real-client accepted. No invented overall operability number.

## Verified operator history
- 2026-10-18: live headed Maps CLI captured Vigo dentists 8/8 and hairdressers 8/8; GUI flow captured 20 selectable records. Real prospect ingestion was not accepted.
- Booking-platform links must not be misrepresented as business-owned websites; `not_observed` is not `no website`. Follow-up GUI verification of new labels remains required.
- 2026-10-16: isolated synthetic commercial lifecycle 14/14 passed; backup/restore isolated snapshot (85 files, SQLite quick_check=ok). Synthetic proof is not a real paying-client journey.
- Operator's local branch, working tree, installed version, current database and full post-merge flow **have not yet been independently inspected in this session**.

## Present acceptance target
1. Safely inspect/synchronize TRON checkout with main without overwriting local changes; protect `%LOCALAPPDATA%\VeridraCommercial`, untracked `infra/` and historic Stripe bindings.
2. Run full local preflight `scripts/windows/VERIDRA_DEV_PREFLIGHT.ps1 -Full`; retain output/exit status.
3. Verify operator startup on loopback, browser prospect capture/review, qualification without uncontrolled live import, bounded audit, evidence and PDF, proposal draft, client/project and monitoring lifecycle, and restart/recovery.
4. Record each gate as PASS, FAIL or NOT RUN, with commit, test fixture/live nature and artifacts. Real outreach/payments/customer-data modifications remain prohibited without explicit approval.

## Durable decisions and conflicting legacy
See `.ai/DECISIONS.md`: the 2026-10-24 operator-only decision supersedes prior active D-012/D-013 dual-SaaS direction **for current work**, but historical records/technical contracts must not be silently deleted. The old H6 Stripe/SaaS provider acceptance, hosted roadmap and pricing are **not current operator launch gates**. Do not resume them absent a new explicit product decision.
Read `veridra.md` and `docs/operations/controlled-development-roadmap.md` for current execution/handover.

## Non-negotiables
- Work outcome-first; after a failure inspect all failed gates and adjacent code, not only the first error.
- Before remote code pushes run local compile, import audit, Ruff, strict mypy and pytest; if unavailable mark LOCAL PREFLIGHT NOT RUN.
- Real external outreach, payments, destructive migration or changing protected customer records need explicit authorization.
- On Windows all provided commands must be path-independent (derive absolute repo path). Never expose credentials, SQLite DB content, backups or untracked `infra/` secrets.
