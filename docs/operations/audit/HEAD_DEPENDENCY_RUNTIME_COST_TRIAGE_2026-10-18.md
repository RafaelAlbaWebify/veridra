# VERIDRA — HEAD dependency and runtime-cost triage (2026-10-18)

## Scope and provenance
- Inspected GitHub branch `refactor/webify-operator-only`, HEAD `88417dd7d09dd8bb05b6086d5fb64332ceee812f`; PR #399 remains draft and unmerged.
- Latest complete CI: run 39106421449 **success**, including Linux and Windows.
- Git tree inventory: **816 entries**, **244** `src/veridra/*.py` modules (**2,137,782 bytes**) and **271** Python test files. These are Git-tree byte counts, **not LOC**. Previous ZIP baseline of 243 modules / 51,902 LOC is a different revision. Do not infer net LOC from it.
- Evidence level: static inspect of `runtime.py`, `application_identity.py`, `agency_monitoring_web.py`, `tenant_offboarding.py`, `runtime_route_policy.py`, `tools/audit_operator_imports.py` and candidate module imports/routes. No exhaustive import graph, dynamic reachability proof, TRON timing trace or local preflight was performed.

## Runtime-boundary observations

| Candidate | HEAD size (bytes) | Static evidence | Triage | Next verification |
|---|---:|---|---|---|
| `monitoring_web.py` | 12,458 | Legacy `/monitoring` router is **not included** by `runtime.py`; `agency_monitoring_web.py` and `tenant_monitoring_api.py` remain included | P1 *removal candidate*, **not proven dead** | Search Python imports, CLI, tools, tests, alternate ASGI app (`app.py`), scripts, backwards-compatible HTTP contracts |
| `auth_api.py` | 4,753 | Defines `/api/auth`; `runtime.py` does **not include** router | P1 candidate | Test references, external calls, account/recovery contracts and alternate entrypoints |
| `browser_auth_web.py` | 15,088 | Defines browser login/recovery routes; `runtime.py` does **not include** router; `application_identity.py` still uses password auth outside operator mode | P1 candidate router only | Differentiate route retirement from required password/session components; avoid deleting auth dependencies |
| `tenant_invitations.py` | 14,029 | Persists invitations; `tenant_offboarding.py` still contains identity/invitation cleanup | **Protected until migration/dependency proof** | Historic data references and invocation path checks |
| `tenant_entitlements.py` | 8,429 | Uses workspace policy, and tests cover seat/entitlement behavior | Needs migration/reconciliation | Check all runtime identities, tests and data migrations before deletion |
| `password_auth.py` | 8,426 | `application_identity.py` imports and instantiates authenticator in non-operator branch | **Active dependency; do not remove blindly** | Decide whether non-operator runtime is supported, then test identity boundaries and backups |

The six files total **63,183 bytes**, not a measured removable-code estimate. Only three routers are immediate *candidates* and even those require full reference verification. Static non-registration in `runtime.py` is insufficient to delete Python modules.

## Additional correctness/security observation
`agency_monitoring_web._monitoring_entitled` defaults to allowed outside `RuntimeEnvironment.production` and consults `TenantWorkspacePolicy`/`PLAN_CATALOGUE` in production only. This is an apparently retained SaaS plan concept in a live agency router. **Do not delete the branch as 'unused' or expand bypass to production** without defining the supported runtime modes and authorization contract. Keep customer capability checks, especially `require_tenant_capability`.

`tenant_offboarding.py` contains a deliberate guard refusing offboarding when historic Stripe binding is present without acknowledged provider-side cancellation. Preserve this safeguard and any historical membership/invitation cleanup or migrator until provider status and recovery are established.

## Recommended high-impact batch sequence
1. **P0 — Discovery reliability/measurement:** collect existing non-sensitive browser stderr + session state once; establish p50/p95 per prospect and failure rate. Fix confirmed Chromium/IPC cause before performance tuning. No repeated live probes without diagnosis.
2. **P1 — Dedicated removal dependency proof:** build a repo-wide graph covering static imports, dynamic imports, `pyproject.toml` scripts, root `.bat`, PowerShell, alternate FastAPI app, CI and test modules. For each of the three router candidates, prove absence of active callers and preserve necessary contracts before removal. Expect validation/migration more than byte-count savings.
3. **P1 — Commercial integrity:** reconcile R02/R03/R04/R05/R06 findings by root cause; prioritize lost writes, ambiguous corruption/not-found, unsafe HTTP/SMTP retries and URL/security boundaries. Fault-injection tests on isolated synthetic stores, no production data.
4. **P2 — Shared visual capture:** baseline calls, browser launches, ZIP exports, output contracts and p95. Consolidate only redundant execution, leaving regulatory and sample-provenance policy explicit.
5. **P2 — UI/DB optimizations:** profile routes, per-page SQL and templates only after profiling; avoid speculative indexing or cosmetic splitting.

## Engineering gates for subsequent changes
- **Gate 0:** one pinned HEAD baseline and proof of active entrypoints, protected state, migration/rollback requirements and acceptance invariants.
- **Gate 1:** local `scripts/windows/VERIDRA_DEV_PREFLIGHT.ps1 -Full` including compileall, import audit, Ruff, strict mypy, full pytest and deterministic audit, before code push. If only remote connector access: **PRE-FLIGHT NOT RUN**, do not treat CI as debugger.
- **Gate 2:** one coherent implementation + tests + docs commit/batch; no unchecked deletions.
- **Gate 3:** Linux and Windows CI success on final head SHA. Real TRON acceptance only for changed functional paths, in one consolidated evidence package.
- **Gate 4:** quantify net source LOC/module changes and p50/p95, CPU/IO/browser count separately. Preserve evidence accuracy, private access controls, backups, Stripe history and commercial data.

## Batch decision
This is a **read-only triage document**; no production code deleted or modified, no claims of faster runtime, no new audit finding considered fixed. Next execution should prioritize Discovery diagnostics and prove removal candidates against the *entire* call graph, not another helper-level microrefactor.


## Batch 2 addendum — router compatibility evidence

Static confirmation against branch HEAD `3c7aa76f1f8461d690cb0c32cf0e76fe722ee60a`:

- `tests/test_monitoring_web.py` imports `veridra.monitoring_web.router` and directly registers it in a test-only FastAPI app, exercising `/monitoring` management routes. The main `runtime.py` does not register that router; `agency_monitoring_web` is separate and active. **Verdict: standalone legacy compatibility route, deletion requires a decision to retire its dedicated API/UI contracts and tests.**
- `tests/test_password_auth_api.py` imports `veridra.auth_api.router` and registers it in a test app, checking password login/session/security behavior. The main runtime does not register this API. **Verdict: candidate route only; password/session model is not necessarily obsolete.**
- `tests/test_browser_auth_web.py` imports `veridra.browser_auth_web.router` and registers it in a test app for login/recovery. This router is also absent from `runtime.py`. **Verdict: test-only compatibility surface; verify non-operator client contract before removing.**
- `runtime_config.py` still supports `RuntimeEnvironment.operator` and private `production + local_agency` mode; `tests/test_operator_runtime_config.py` enforces loopback restrictions, and `application_identity.py` initializes password/session dependencies outside operator mode. **Do not delete `password_auth.py`, session or identity state simply because ordinary operator mode bypasses them.**
- `runtime_route_policy.py` describes standalone legacy route families, but merely listing a prefix is **not proof** that its backing modules can be deleted.
- `agency_monitoring_web._monitoring_entitled` consults a workspace plan in production, while operator/non-production takes the allowed path. Before eliminating `tenant_entitlements` or `workspace_policy`, explicitly define the supported authorization semantics for both private runtime configurations.
- The offboarding guard for historical Stripe bindings remains mandatory.

**Gate status:** main-runtime non-registration plus test-only registration observed; repository-wide dynamic/launcher reference absence **not proven**. No router deleted in Batch 2. Next: automated complete-reference enumeration (Python AST + pyproject entrypoints + Windows scripts + BAT + dynamic strings), then isolated removal test and Windows acceptance if the product decision retires compatibility mode. Do not remove tests merely to make CI green.
