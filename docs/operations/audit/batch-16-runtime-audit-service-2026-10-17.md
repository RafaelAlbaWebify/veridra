# VERIDRA functional audit — Batch 16: Runtime wiring, security headers and audit service

Baseline: uploaded ZIP snapshot, potentially preceding current GitHub commits. Date: 2026-10-17. **12 new, unique source modules, 2,103 physical lines**: `runtime.py`, `runtime_email.py`, `runtime_legal.py`, `runtime_route_policy.py`, `security_headers.py`, `access_logging.py`, `passive_security.py`, `production_preflight.py`, `health_web.py`, `operations_api.py`, `ops_check.py`, `service.py`.

Reviewed module-level configuration, app import-time side effects and router ordering, runtime profile branches, HTTP middlewares, route concealment, logging/error paths, readiness/preflight checks, passive security rule semantics, and end-to-end `assess_url()` orchestration (collector, crawl, DNS, findings, observed assessment). No app code changed.

## Findings — reconcile to current remote version

- **F105 / P1 — route hiding relies on include order and path string removal.** `runtime.py:100-192` registers multiple base and wrapper routers in profile-dependent order; `runtime_route_policy.py:49-60` removes operator-excluded paths only at the end. Directly calling `FastAPI.app.routes` vs actual HTTP routing, and future refactors to duplicate paths, can change effective endpoint. Maintain explicit route-inventory tests for operator and local agency, including method/path/handler identity.
- **F106 / P2 — legacy route concealment helper is defined but not called in normal runtime.** `runtime_route_policy.py:39-46` implements `conceal_legacy_browser_routes`, yet `runtime.py` imports only `conceal_operator_excluded_routes`. This is a candidate for unused compatibility code after tracing direct call/test references; not proof obsolete across all CLI/test entrypoints.
- **F107 / P2 — security CSP differs across embedded/market paths.** `security_headers.py:32-91` permits `frame-ancestors` only for market map and omits X-Frame-Options for `/embed/`. Intentional product feature, but correctness depends on matching `/embed/` endpoints' access control and actual map route pattern. Verify with integration tests before tightening.
- **F108 / P2 — HSTS set for private HTTP production loopback.** `security_headers.py:79-86` sends `Strict-Transport-Security` whenever environment is production; `runtime_config.py` permits only HTTP loopback production. HSTS browsers ignore insecure transport headers; this is misleading hardening evidence and should not be counted as effective TLS security.
- **F109 / P2 — readiness checks cover dependencies, not actual browser availability.** `health_web.py:57-84` and `operations_api.py:41-51` verify runtime identity/store availability but do not probe headed Playwright/Google Maps. Thus green readiness and CI cannot certify Find Prospects. Add *separate*, non-disruptive browser capability check rather than launching a GUI in every HTTP readiness call.
- **F110 / P2 — SMTP initialization includes retired identity adapters.** `runtime_email.py:14-56` sets password-reset and tenant-invitation adapters if SMTP configured, although hosted login/invite routes are unmounted from the private runtime. This is candidate extra initialization/dependency surface; preserve historical evidence and ensure other consumers before removal.
- **F111 / P2 — passive-security heuristics are indicators, not vulnerability proof.** `passive_security.py:104-236` reports cookie flags, forms, external resources, CSP and server disclosures from collected HTML/headers; no browser DOM execution. Ensure customer-facing reports describe heuristic evidence without claiming verified penetration-testing.
- **F112 / P2 — large audit service orchestrator couples many analyzers.** `service.py:323-412` coordinates HTTP, robots, crawl, security, quality, accessibility, DNS and reporting sequentially; failure in later DNS/subsystem can abort assessment after expensive crawl. Need targeted fault isolation, truthful partial-result provenance and bounds; not permission to suppress all exceptions.

## Positive controls
- Runtime uses localhost-bound deployment config and proper trusted-host, request-body and identity middleware.
- Security headers default CSP denies scripts and frames; market map exceptions are narrow.
- Access logging avoids raw URL, query params and body, emits opaque request IDs, and keeps request handling alive on logger failures.
- Preflight reports per-dependency diagnostics and intentionally treats private Webify differently from public SaaS.
- `assess_url` enforces a single choice of crawl profile or explicit limits and uses remote-target safety via collector.

**Validation:** shared local ZIP gate with Batch 15: 43 tests passed across quota/offboarding/identity/preflight/headers/runtime hardening. No live website audits or TRON browser starts performed. Report only source-level review, not all-branch execution or production correctness.
