# Runtime route policy

VERIDRA contains historical and compatibility code for more than one product shape. The supported Webify runtime is operator-local and must not expose those shapes as one mixed journey.

## Operator-local runtime

When VERIDRA_ENV=operator:

- bind host must be loopback;
- the sole active local owner may be resolved automatically;
- / redirects to /agency;
- /agency/* is the authoritative browser workflow;
- tenant-qualified internal APIs may support that workflow;
- health/operations endpoints remain available for runtime checks.

The operator runtime deliberately excludes normal browser exposure of:

- /free freemium tools;
- /login, /signup and /onboarding;
- workspace/plan/team/member surfaces;
- public lead forms and inbound lead workflow;
- SaaS Stripe billing UI;
- standalone /crawl/*, /report, /report.pdf and /export;
- legacy process-global browser trees.

## Primary operator browser entry points

- /agency
- /agency/prospects
- /agency/prospects/discover
- /agency/deals
- /agency/customers
- /agency/projects
- /agency/recurring-services

Project/prospect descendants implement the supported workflow.

## Non-operator compatibility

Historical SaaS, public-tool and standalone modules may remain in the repository and may be composed deliberately outside operator mode for tests, compatibility or future product experiments. Their existence in source does not make them part of the supported Webify product.

## Safety rules

- operator mode must not depend on SaaS plans, seats or subscriptions;
- payment state inside VERIDRA is a bounded operational mirror, not provider/accounting authority;
- no browser route may infer protected ownership from client-supplied tenant identity;
- direct URLs must enforce the same commercial/privacy gates as visible buttons;
- duplicate HTTP method/path registrations for business-state transitions are prohibited;
- a legacy route must not be linked from operator navigation;
- adding a route to operator mode requires a clear operator use case and regression test.
