# Veridra assessment rules

Veridra performs bounded, passive checks against public website responses. Findings must be deterministic, evidence-backed, and explicit about unavailable evidence.

## Current rule groups

- Website health: homepage response, document title, mobile viewport, primary heading.
- Search visibility: canonical URL, robots.txt availability.
- AI discoverability: JSON-LD presence and OAI-SearchBot access.
- Public security posture: HSTS, Content-Security-Policy, and X-Content-Type-Options.

## Rule constraints

- A missing control is not automatically a vulnerability.
- A passed public check does not prove that a website is secure.
- robots.txt directives must be interpreted per user-agent group rather than by substring matching.
- Header names are case-insensitive.
- Target-derived evidence must be escaped before HTML rendering.
- Active testing, authentication, form submission, port scanning, and exploit payloads remain excluded.
