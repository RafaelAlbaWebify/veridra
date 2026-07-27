# Runtime route policy

Veridra supports two distinct browser contexts. They must not be presented as one mixed operator journey.

## Composed commercial runtime

`veridra.runtime` is the authenticated multi-tenant product runtime.

Authoritative browser surfaces:

- `/agency` — authenticated operator home and quick-audit workflow;
- `/agency/projects` and project-attached descendants — persistent client work;
- `/agency/leads` and lead conversion — captured prospect workflow;
- `/workspace`, `/members` and `/members/audit` — tenant plan, usage, membership administration and operator audit evidence;
- `/onboarding`, `/login` and recovery/session pages — identity lifecycle;
- `/embed/audit/{form_id}` — public tenant-bound lead capture;
- `/tools/*` and the bounded assessment entry points — public or temporary tools.

Tenant APIs remain under `/api/tenant/*`. Other `/api/*` routes are operational APIs and are not primary browser navigation.

The composed runtime excludes standalone compatibility route trees rooted at:

- `/commercial`;
- `/history`;
- `/lead-forms`;
- `/leads`;
- `/monitoring`;
- `/profiles`;
- `/projects`;
- `/tasks`.

Their source modules and stored standalone data are not deleted. The exclusion prevents the hosted tenant runtime from exposing process-global browser pages or write actions alongside tenant-qualified agency workflows.

## Standalone compatibility

The legacy routers and `veridra.app` remain available for local or standalone compatibility. Their process-global files are not tenant state and are never automatically attached to an authenticated tenant.

Examples include standalone project, task, history, profile, lead-form, monitoring and commercial pages. Applications that intentionally include those routers directly retain their GET and POST routes.

## Safety boundary

- No browser route may infer a tenant from a URL or client-supplied identifier.
- Agency pages require verified request identity where tenant data is involved.
- Process-global compatibility writes are unavailable in the composed tenant runtime.
- Public embedded forms resolve the tenant from a server-side form binding.
- Standalone compatibility must not be described as the authoritative hosted SaaS workflow.
