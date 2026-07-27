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

Tenant APIs remain under `/api/tenant/*`. Other `/api/*` routes are operational or compatibility APIs and are not primary browser navigation.

The composed runtime conceals duplicate legacy GET/HEAD browser pages rooted at:

- `/commercial`;
- `/history`;
- `/lead-forms`;
- `/leads`;
- `/monitoring`;
- `/profiles`;
- `/projects`;
- `/tasks`.

This concealment does not delete their source modules, POST handlers or APIs. It prevents the commercial runtime from advertising multiple competing browser journeys.

## Standalone compatibility

The legacy routers and `veridra.app` remain available for local or standalone compatibility. Their process-global files are not tenant state and are never automatically attached to an authenticated tenant.

Examples include standalone project, task, history, profile, lead-form, monitoring and commercial pages. Applications that intentionally include those routers directly retain them.

## Safety boundary

- No browser route may infer a tenant from a URL or client-supplied identifier.
- Agency pages require verified request identity where tenant data is involved.
- Hiding a legacy GET page does not authorize its POST action; normal middleware and endpoint capability checks still apply.
- Public embedded forms resolve the tenant from a server-side form binding.
- Standalone compatibility must not be described as the authoritative hosted SaaS workflow.
