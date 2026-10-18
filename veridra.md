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


## VERIDRA 21 — Mandatory complete-failure sweep and Discovery handover (2026-10-18)

**Product goal and freeze.** Restore **real headed Google Maps capture on TRON** before any other development, then prove one real-prospect audit/report/proposal draft with no outreach, payments or production-data modification. Avoid manual import as a substitute for repairing the regression. PR #399 is unmerged; never merge without explicit permission.

**User-mandated debugging rule (NON-NEGOTIABLE): NEVER stop at the first error.** After detecting any CI, test, runtime or acceptance failure:
1. Read **all failed jobs, full failure outputs and relevant artifacts**, not merely the first reported error or the step that blocks downstream checks. Mark downstream gates as **NOT RUN**, not passing.
2. Diagnose the root cause and **sweep the entire current change surface**, reviewing adjacent code, imports/types, branching, exceptional paths, tests, CLI/launcher contracts, security, Windows portability and runtime behavior for further likely failures.
3. Before making another functional push, run the **whole local preflight**, ideally `scripts/windows/VERIDRA_DEV_PREFLIGHT.ps1 -Full` (compileall, import integrity, Ruff, strict mypy, complete pytest, deterministic audit). Do not mistake GitHub CI for a preflight or claim that a static review executes tests. If environment has only remote GitHub connector: say **LOCAL PREFLIGHT NOT RUN**; do not keep pushing one speculative patch after another.
4. Correct all discovered errors coherently in a **single batch** of code, tests and only necessary documentation. Check passing Linux **and** Windows jobs for the exact final SHA. Do not let cancellation of intermediate runs count as success.
5. After **two avoidable CI failures**, stop feature work, conduct comprehensive gate-by-gate review and request/obtain an executable local preflight path before resuming. Do not enter an endless CI-patch loop.
6. Reporting: very short quantified facts plus **acceptance-gate percentage with denominator**, not invented product-readiness estimates. Count operational Google Maps restoration as **0% verified until one real TRON capture passes**. Distinguish implementation, green CI and live acceptance.

**Incident record: automatic capture CLI, Oct 18.**
- Existing `veridra-assisted-discovery-check` was manual (`input()`); browser UI acceptance `scripts/browser/discovery_workflow_acceptance.py` uses fixtures and **does not validate real Maps capture**.
- Added opt-in `--automatic` and bounded `--settle-seconds` to `src/veridra/assisted_discovery_acceptance_cli.py` plus zero-results failure and synthetic tests; existing `VERIDRA_DISCOVERY_CHECK.bat` can invoke it. This does not change real prospect data.
- **Avoidable CI failure #1**: run 39126036745, Linux `verify` failed Ruff I001 (unsorted test imports); Windows `windows-portability` passed.
- **Avoidable CI failure #2**: run 39126450715, Linux `verify` failed strict mypy with **two errors**: inferred heterogeneous payload dictionary refused boolean `acceptance_passed`, and tests accessed `acceptance.time` not explicitly exported. Windows passed.
- Corrected payload annotation `dict[str, object]`, test monkeypatch via module-qualified string, import sorting, added invalid settle-seconds regression check. Final HEAD `916513de75645c2c3a3ffae6a30274b94bf4c347` passed **both CI jobs** in run [39126938523](https://github.com/RafaelAlbaWebify/veridra/actions/runs/39126938523). **LOCAL PREFLIGHT NOT RUN for this last batch; real Google Maps TRON acceptance still NOT RUN**. Green CI is not equivalent to operational recovery.
- Earlier startup adjustment `edb2ae4d1a6a`: Chromium reports readiness after creating visible page, before initial slow Maps navigation, with a regression test; associated CI previously passed. This addresses a plausible startup wait, not proven source of live regression.
- Manual legacy prospect save bug also corrected separately (`6944f0e`), but **do not work on other features until Google Maps works**.

**Immediate next action**: execute ONE bounded noninteractive headed live Maps capture on TRON with an isolated profile, using `VERIDRA_DISCOVERY_CHECK.bat --query "dentistas Vigo" --country-code ES --locality Vigo --automatic --max-results 8`, capturing exit code/output and local browser stderr. Passing condition: actual nonempty, meaningful Google Maps observations and no browser/IPC crash. If failed, analyze the **complete bundle**, find root cause, inspect the complete affected module chain and run full preflight before committing any further fix. Do not repeat attempts without new diagnostic information.


## VERIDRA 21 — TRON live Google Maps recovery accepted (2026-10-18)
- **LIVE ACCEPTANCE PASSED TWICE**, headed Chromium, persistent isolated acceptance profile, no login repeated: query `dentistas Vigo` returned 8/8 unique businesses (`state=review`, `max_results`, `automatic_live`, `acceptance_passed=true`); second query `peluquerias Vigo` returned 8/8 unique businesses, 1 scroll, ~6.486 seconds collection, exit 0. Together 16 observations, 16 distinct provider keys, 8 reported websites, 8 categories missing. No CRM persistence (`persistence=none`), no outreach or payments. Basic browser launch, readiness and scrolling/capture **operationally validated**.
- Quality follow-up (not blockers of baseline recovery): accented names display mojibake in Windows PowerShell native pipeline (e.g. `Ana Mar├¡a Gil`); assess source JSON versus PowerShell decode before changing extractor. Categories missing in 8/16; website absent in 8/16 means **not observed**, NOT proven no website, and booking links such as Fresha/Booksy are not necessarily owned business websites. Improve metadata and qualification truthfulness with tests; no assumption that all empty fields denote no digital presence.
- Do not resume repeated recovery changes now that baseline passed. Continue bounded data-quality improvements only after diagnostics and complete gate-by-gate validation. Mandatory rule: investigate all failures and relevant surfaces, never just first failing CI gate.
