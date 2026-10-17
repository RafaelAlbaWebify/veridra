# VERIDRA — Functional audit / Batch 01: Discovery

Date: 2026-10-17. Source baseline: user-supplied `VERIDRA_SOURCE_AUDIT.zip`, **not guaranteed to match the latest GitHub head**. This audit is evidence and repair planning only; no production acceptance is inferred.

## Progress

- Full semantic read-through of **7 / 243 production Python modules (2.88%)**, roughly **1,629 lines**. Other 236 are **not** counted as line-by-line reviewed.
- Reviewed: `assisted_browser_protocol.py`, `assisted_browser_provider.py`, `assisted_browser_runner.py`, `assisted_discovery.py`, `assisted_google_maps.py`, `assisted_discovery_acceptance_cli.py`, `prospect_discovery.py`.
- 29 focused tests passed on the ZIP snapshot, including browser provider, discovery manager, Google Maps quality, discovery CLI and prospect discovery. Tests do **not** verify real headed Chromium on TRON.
- End-to-end interfaces followed: acceptance CLI → manager → subprocess provider → browser runner → Google Maps extraction → ordered observation accumulator → IPC → validation → candidate output. UI, Market Study persistence and CRM are **not** counted in this batch.
- External/frontend, SQL migrations, Windows launchers and test suites are excluded from the percentage denominator: the denominator covers `src/veridra/*.py` production modules only.

## Findings — keep identifiers stable across batches

### F01 [P0] Browser startup incorrectly considered successful (OPEN)
`assisted_browser_provider.py`, launch around lines 63–90: checking `Popen.poll() is None` immediately does **not** mean Playwright launched Chromium. The runner opens a persistent context and navigates later (`assisted_browser_runner.py`, around 134–142). The CLI can therefore tell an operator that a browser is open while it is exiting. **Repair criterion:** explicit runner → parent startup handshake (`ready` / `launch_error`) with timeout, and UI/CLI state based on acknowledgement. Root cause of observed TRON exit remains unconfirmed.

### F02 [P1] Response-reader threads can survive timeout (OPEN)
`assisted_browser_provider.py`, around 220–244: each request spawns a daemon blocked on `stdout.readline()`. Timeout does not cancel the reader or necessarily invalidate the subprocess; a later read may compete for a reply. **Repair criterion:** on timeout, invalidate process/channel or use exactly one owned response reader; verify timeout followed by retry.

### F03 [P1] Process exit race before stdin write (RECONCILE REMOTE)
`assisted_browser_provider.py`, around 127–152: `poll()` may pass, then child exit before `write_message`, yielding `BrokenPipeError`. Reported fixed in later remote branch by mapping write errors to `VisibleBrowserUnavailable`; re-read current head and tests before claiming resolved.

### F04 [P0] Initial Maps navigation can kill session (RECONCILE / TRON UNVERIFIED)
`assisted_browser_runner.py`, around 134–142 in ZIP: initial `page.goto` is outside the subsequent per-request error handlers. Timeout/navigation error unwinds runner and closes context. Later branch changed navigation error handling, but **actual** TRON Chromium success is not established. Avoid generic catch that hides the inability to reach Maps.

### F05 [P1] Failed collection marks dead browser as ready (OPEN)
`assisted_discovery.py`, collection around 284–324 and `_restore_ready_after_error` around 348–363: *all* collection failures restore `state=ready`, including EOF/child-exit transport failures. **Repair criterion:** recoverable page/selector failures stay operable only when process lives; child death causes terminal state and cleanup. Compare web registry lifetime and exception paths as one transaction.

### F06 [P1] Weak Google Maps URL origin check (OPEN)
`assisted_google_maps.py`, capture/traversal around 178–194 and 300–310: textual `'google.' in page.url` and `'/maps' in page.url` do not establish a permitted hostname. **Repair criterion:** `urlsplit`, explicit Google hostname policy and Maps path validation; tests for lookalike hostnames and unexpected paths. There is no evidence of exploitation.

### F07 [P2] Detail-page enrichment can overshoot collection budget (OPEN)
`assisted_google_maps.py`, detail/capture around 127–175, 178–269: per-card secondary navigation (up to ~5 s each plus reads) can dominate a bounded collection; time is checked after work in a traversal iteration. Failure yields empty metadata and caches that absence. **Repair criterion:** shared time budget across detail calls; provenance distinguishes missing from failed extraction; no unsupported claims of observed data.

### F08 [P2] Fallback identity can merge same-name businesses (OPEN)
`assisted_google_maps.py`, identity around 52–68 and `prospect_discovery.py`, dedup around 123–134: fallback provider key from name alone can collide for distinct businesses without a Maps URL. **Repair criterion:** use further geographical/source evidence or retain ambiguity; never silently merge uncertain identities.

### F09 [P2] IPC size bounded only after unbounded readline (OPEN)
`assisted_browser_protocol.py`, around 31–42 imposes 256 KB decode limit, but provider's `readline()` may allocate more before it checks length. **Repair criterion:** bounded line reader and controlled child termination if exceeded.

## Notes for eventual implementation
1. This is **ZIP-baseline evidence**. Before editing, compare each ID with `refactor/webify-operator-only` latest head and mark `confirmed_current`, `fixed_unverified`, or `not_applicable`.
2. Fix by interface contracts (provider/runner/manager/web registry), not isolated exception-catching patches. Preserve review data and write transaction boundaries.
3. Record proofs (test name, commit, CI SHA, TRON acceptance only when actually run) against the finding ID; never mark fixed on CI alone for headed Chromium.
4. Avoid deleting modules solely because static references are absent. Historical Stripe, tenant data, backup and migration files need explicit retention review.
