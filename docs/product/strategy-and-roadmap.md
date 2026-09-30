# Veridra product strategy and roadmap

## Canonical product position

VERIDRA is the operator-local internal application used by Webify to turn public digital-presence evidence into qualified opportunities, bounded customer work and recurring Presence Care.

It is not currently a hosted SaaS product and it is not a customer portal.

Canonical runtime:
- Windows operator workstation;
- loopback-only browser application;
- one Webify operator workspace;
- customers do not sign in to VERIDRA;
- customer communications, signatures and provider payment events remain external unless explicitly integrated;
- external services are used only where they add business value, not to host VERIDRA.

## Core commercial loop

1. discover real businesses;
2. qualify commercial fit;
3. run a bounded prospect audit;
4. pass the outreach/privacy compliance gate;
5. record conversation and discovery;
6. create, send and track a bounded proposal;
7. convert accepted proposal evidence into customer onboarding;
8. require accepted terms and required payment evidence before delivery work starts;
9. create and execute the client project;
10. produce evidence-backed reporting and remediation work;
11. verify customer acceptance, handoff and closure;
12. activate and manage recurring Presence Care where justified;
13. re-assess and prove changes over time.

## Evidence model

Observation → evidence → affected URLs → business impact → recommended fix → task → rescan verification.

Commercial lead scoring never overrides the outreach-compliance gate.

## Operator surfaces

Primary: operator home; prospect discovery; qualification/audit/outreach eligibility; sales/proposals; customers/onboarding; client projects; reports/remediation/monitoring/progress; delivery/acceptance/handoff; recurring Presence Care.

Advanced/secondary: manual prospect import; crawl-profile tuning; AI review exchange; optional SMTP report delivery.

## Explicitly excluded from operator-local runtime

The repository may retain compatibility modules, tests and prior SaaS foundations, but the supported operator product does not expose public signup/onboarding, browser login as a normal step, workspace plans/quotas/seats, team administration, public freemium tools, inbound lead capture, SaaS Stripe plan billing, public hosting requirements or customer VERIDRA access.

## Current priority

The priority is operator-product hardening, not feature expansion:

1. remove stale SaaS/standalone surfaces;
2. ensure every state transition enforces server-side commercial/compliance gates;
3. eliminate duplicate route authorities and dead links;
4. make the workflow understandable without product-history knowledge;
5. keep CI and operator acceptance green;
6. run a controlled real-prospect discovery exercise before reopening outreach.

## Completion measure

VERIDRA is ready only when a Webify operator can complete:

prospect → qualification → audit → outreach eligibility → conversation → proposal → customer/payment gate → project → delivery → acceptance → recurring/proof

Repository module count, route count and synthetic happy-path tests are not sufficient readiness measures.
