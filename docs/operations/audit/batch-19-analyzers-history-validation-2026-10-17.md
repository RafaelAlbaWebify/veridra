# VERIDRA functional audit — Batch 19: analyzers, longitudinal evidence and historical validation

**Source baseline:** user-provided local ZIP snapshot, not necessarily latest GitHub HEAD. **10 unique modules, 1,944 physical lines:**
`dns_posture.py` (293), `accessibility.py` (296), `business_content_consistency.py` (346), `longitudinal.py` (97), `history_web.py` (248), `smb_validation_compare.py` (243), `recovery_readiness_cli.py` (44), `backup_restore_cli.py` (93), `ops_check_cli.py` (62), `production_preflight_cli.py` (25).

Reviewed inputs/output contracts, analyzer control flow, attribution, exception/error handling, CLI side effects, retained evidence lifecycles, and cross-component storage/use. Executed **44 local ZIP tests** for DNS, accessibility, business-content consistency, longitudinal findings, historical web screens, SMB validation and preflight. No live domain crawl, restore, pruning or customer operations occurred. **Cumulative unique coverage 170/243 = 69.96%; 73 modules pending.**

## Findings (historical ZIP baseline; current-head confirmation required)

- **F127 / P2 — Nameserver redundancy scoring conflates distinct NS records with independent infrastructure.** `dns_posture.py:143–163` marks pass for `len(nameservers)>=2` and recommends independent infrastructure on fewer than two, but two NS names do not prove independent networks/operators. Present as an observation rather than proved resilience. No DNS safety exploit claimed.
- **F128 / P2 — Opening hours heuristic may generate false cross-page conflicts.** `business_content_consistency.py:247–334` compares day/value strings from visible HTML across crawled pages without clear branch/location identity; independently valid hours on two office pages can appear inconsistent. Preserve evidence and caveat that human/local context is required.
- **F129 / P2 — Accessibility is explicitly static signal extraction.** `accessibility.py:216–296` flags heading gaps, labels, alts, language, viewport and duplicate IDs from crawler evidence; no browser DOM/assistive tech execution. Ensure report messaging does not claim WCAG certification. This is scope/marketing correctness, not a confirmed implementation bug.
- **F130 / P2 — History prune route uses a fixed keep count without contextual guard.** `history_web.py:136–159` renders retention form `POST /history/prune?keep=20`; the route is a historical surface separate from tenant-scoped project history. Determine normal runtime inclusion and backup/legal retention policy before treating as active. No pruning executed.
- **F131 / P2 — Observation lifecycle intentionally reports incomplete pre-observation history.** `longitudinal.py:57–97` declines to fabricate first/last-seen dates if any retained assessment predates normalized observations. Positive integrity control. Avoid 'fixing' missing timestamps with assumptions.
- **F132 / P2 — Validation CSV compares businesses by display name.** `smb_validation_compare.py:17–39,128–170` associates audit ZIP assessment to `business_name` strings. Two businesses with identical names can collide, conflating adjudications. Use provider/source stable IDs when supplied, preserve older name-only evidence as ambiguous.
- **F133 / P2 — CLI interfaces lack common read-only/default safeguards.** `backup_restore_cli.py:56–88`, `recovery_readiness_cli.py:21–40`, `ops_check_cli.py:37–58` expose different operational gates and output formats; avoid consolidating them without explicit dry-run and destructive-action compatibility testing. Architectural opportunity, not demonstrated defect.

## Positive controls
- The lifecycle logic preserves historical uncertainty rather than inferring nonexistent records.
- DNS posture reports lookup-unavailable separately from absence; a timeout is not mislabelled a missing MX.
- SMB validation differentiates not-assessed from negative findings and tracks positive/negative hit rates.
- Existing report findings are typed, and historical web route escapes displayed target fields.
- Backup restore CLI requires explicit operator flags; no automatic destructive restore is performed by the audit.

## Audit standard
Source-level module-by-module semantic review and linked test selection; **not** 100% dynamic path coverage. All IDs describe ZIP-baseline code; before repairs verify each with branch head and specific failure reproductions. No application code changed.
