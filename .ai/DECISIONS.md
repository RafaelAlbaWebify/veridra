# Durable Decisions

## D-001 — Evidence-first product boundary
Decision: use bounded public observations and explicit evidence; do not claim exhaustive SEO/security/AI visibility.
Reason: accuracy, safety and defensibility.
Status: active.

## D-002 — VERIDRA supports Webify; it is not the commercial identity
Decision: customers buy Webify service outcomes; VERIDRA is the agency/internal platform.
Status: active.

## D-003 — Recurring-first Presence Care
Decision: initial commercial model prioritizes recurring care with a bounded activation and monthly included work allowance.
Status: active; customer-facing legal approval still pending.

## D-004 — Single-writer persistence initially
Decision: SQLite + filesystem state is acceptable for first deployment if operated single-writer.
Alternative: distributed/shared persistence now.
Reason: avoid premature infrastructure complexity.
Reconsider when concurrency/scale requires it.

## D-005 — Separate web and monitoring worker processes
Reason: monitoring durability and supervision boundaries.
Status: active production requirement.

## D-006 — Provider-neutral deployment
Decision: repository supplies container/runtime contracts but does not hardcode a cloud vendor, DNS, TLS, ingress or secret manager.
Status: active.

## D-007 — Stripe is payment/subscription authority; VERIDRA is not accounting ledger
Decision: external billing/invoice/payment evidence controls; VERIDRA stores references/mirrored operational state only.
Status: active.

## D-008 — No secrets/sensitive health data in ordinary workflow storage
Decision: use delegated/role/temp/password-manager access; no passwords/MFA/full card details/PHI in ordinary VERIDRA, Docs, GitHub or unapproved AI tools.
Status: active.

## D-009 — Production signup only; onboarding bootstrap non-production
Decision: `/signup` is public production registration; `/onboarding` must remain hidden in production.
Status: implemented/tested.

## D-010 — Synthetic lifecycle is not real-world readiness
Decision: #285–#289 engineering remains valid, but outreach is blocked by #284/#296 until deployment/providers/legal/dry-run/human gates pass.
Reason: prior readiness claim overreached synthetic evidence.
Status: active hard gate.

## D-011 — Initial market/vertical
Decision: English-speaking international markets; first controlled validation uses independent dental practices, starting with Ireland before wider expansion.
Status: business direction, not a code constraint.