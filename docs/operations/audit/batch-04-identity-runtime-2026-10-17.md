# VERIDRA — Functional audit Batch 04: Identity and runtime boundaries
2026-10-17; ZIP baseline, possibly older than GitHub branch. **8 additional modules; cumulative 34/243 = 13.99%**. Application changes: none.

## Modules covered
- `identity_tenancy.py` (237): user/tenant/membership/session model, active and scope checks, role→capability mapping.
- `identity_middleware.py` (47): authenticated adapter and unsafe-method origin validation.
- `application_identity.py` (140): loopback single-owner SQLite resolver, session/local fallbacks.
- `request_security.py` (77): request identity binding, role guard, 404 for cross-tenant refs.
- `same_origin.py` (114): Origin, Referer, null-Origin on loopback, public embed exemption.
- `session_identity_adapter.py` (80): opaque credential store, live identity revalidation.
- `runtime_boundary.py` (104): bounded unsafe-request body, forwarded-header peer trust, schema concealment.
- `runtime_config.py` (210): absolute paths, allowed hosts, port/body bounds, private loopback profiles.

## Findings (pending validation against current remote SHA)
- **F25 P2 — Public embed prefix excluded from unsafe-method origin protection**: `same_origin.py:11,82–108`. Validate actual embed endpoint authorization and whether POST paths below `/embed/audit/` can mutate state. Do NOT claim exploit; static policy observation.
- **F26 P2 — Identity-binding contract depends on trusted middleware order**: `identity_middleware.py:24–44`, `request_security.py:23–45`. Check app wiring, alternate profile and any public/test injection path before drawing conclusions. Existing server-side session identity is revalidated, a positive control.
- **F27 P2 — localhost disagreement in loopback checks**: `runtime_config.py:68–98,162–208`. `is_loopback_local` treats `localhost` as loopback, but `validate()` requires `ip_address(parsed.hostname)`, so hardened origin localhost is rejected. May be deliberate strictness; document/explain or normalize.

## Evidence
**43 focused tests passed** on local ZIP for identity tenancy, identity middleware, same origin, session identity adapter, operator runtime config. No real live/browser test. Good existing controls: role and tenant separation, cookie credential server-side revalidation, single owner count, bounded request size, explicit loopback-only production mode. No code removal recommended on name or import count alone.

Next: project and task stores, audits, reports, monitoring; reconcile earlier ZIP finding IDs with current code prior to implementation.
