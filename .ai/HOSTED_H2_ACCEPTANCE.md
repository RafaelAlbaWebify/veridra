# Hosted H2 commercial UX acceptance

Status: **COMPLETE**
Closed: 2026-10-02

## Scope

H2 makes the hosted agency product coherent and recoverable at the browser/UI boundary without weakening the H1 entitlement, metering or tenant-isolation guards.

This is not live-host or provider acceptance.

## Closure baseline

- Final H2 head: `fd31827e`
- GitHub Actions run: `36998742301`
- Result: **success**
- Verify: Ruff, strict mypy, pytest, deterministic audit and discovery acceptance passed.
- Windows: portability, sales-contract Playwright and full operator Playwright acceptance passed.

## Accepted UX boundaries

| Area | H2 result |
| --- | --- |
| Hosted product IA | Production navigation is focused on agency audits/projects, inbound leads/forms, reports/tasks/monitoring, team and plan/billing. Webify outbound prospecting, customer work-start/billing workflow and Presence Care browser routes are operator-only. |
| Home entitlements | White-label, embedded forms and recurring monitoring are described from the active plan rather than advertised unconditionally. |
| Audit quota | Hosted home checks the real usage ledger/reservations before presenting Quick Audit; exhausted/suspended state points to Plan & usage instead of a predictable 429. |
| Project capacity | Home, direct-audit conversion and lead conversion expose a recoverable capacity state before project creation. Server-side H1 enforcement remains authoritative. |
| Report profile downgrade | Default Veridra profile remains a recovery path while white-label create/edit/use is locked by plan. |
| PDF/export UX | Report hub checks real PDF/export allowance before exposing actions; HTML preview remains available after QA where appropriate. |
| Team seats | Invite form is hidden when no seat is available; non-owner deactivation and upgrade guidance remain available. |
| Billing unavailable | GET /billing remains useful when Stripe is not configured; provider mutations still fail closed. |
| Lead conversion | Hosted Lead -> Project is project-native and no longer creates the operator-only Customer onboarding record as a hidden side effect. |
| Lead provenance | Inbox/detail show tenant-scoped source form and submission timestamp and remain readable after the source form is deleted. |
| Embed origin flow | Allowed parent origins admit the iframe load while the form's trusted Veridra same-origin postback is accepted; unrelated origins remain blocked. |
| Embed setup | Agency-plan forms expose a dedicated Setup page with absolute production URL, iframe snippet, parent-origin guidance and a verification checklist. |

## Important preserved guards

H2 did not replace H1 controls:

- POST/API entitlement and quota checks remain authoritative;
- tenant isolation remains store-qualified;
- suspended workspaces remain blocked from commercial mutation;
- lead capture remains tenant-bound and metered;
- team seat acceptance remains transactional;
- operator-local workflow remains separately regression-tested.

## Product-boundary cleanup

Hosted browser runtime no longer exposes these Webify operator workflows:

- Customers / agreement / deposit / work-start gate;
- outbound prospect discovery and sales/proposals;
- commercial dashboard derived from the Webify customer model;
- Presence Care / recurring-service lifecycle.

The underlying historical modules remain available to `VERIDRA_ENV=operator` where applicable.

## What H2 does not prove

H2 does not prove:

- professional report/PDF polish beyond the existing renderer;
- 500-page asynchronous crawl scale;
- real Stripe or SMTP provider lifecycle;
- actual hosted HTTPS deployment behavior;
- human acceptance on a real hosted instance;
- final public pricing.

Those belong to H3+.

## Next phase

**H3 — Report polish**

Existing report capability already includes:

- branded cover;
- reusable saved report profiles;
- executive summary;
- priority actions;
- business-impact view;
- implementation roadmap;
- assessment areas;
- affected-page evidence;
- print CSS;
- Playwright PDF;
- footer page numbers.

H3 should extend that existing renderer rather than rebuild it:

1. navigable table of contents;
2. compact status/area visualization using bounded report data only;
3. deliberate print/page-break behavior for long reports;
4. section presets over existing reusable profiles;
5. preview/PDF regression evidence.
