# Durable Decisions

## Current decision priority — D-014 (2026-10-24)
**VERIDRA is the private Webify operator, not an independently marketed SaaS in the current phase.** PR [#399](https://github.com/RafaelAlbaWebify/veridra/pull/399) was merged to main on 2026-10-24 alongside the Engineering Harness. The primary workflow is Webify prospect discovery → qualification → evidence-backed audit → report → proposal draft → delivery/projects/remediation/monitoring, with controlled customer billing.

This supersedes the **current execution priorities** of historical D-012 and D-013 and the public-signup portion of D-009. It **does not** authorize destructive removal of legacy records, external Stripe actions, public outreach or resurrection of hosted functionality. Historical SaaS decisions remain below for provenance.

## D-001 — Evidence-first product boundary
Use bounded public observations and explicit evidence. Do not claim exhaustive SEO/security/AI visibility. **Active.**

## D-002 — VERIDRA supports Webify; it is not the commercial identity
Customers buy Webify outcomes. **Reaffirmed as current direction by D-014.** Previously superseded during SaaS planning.

## D-003 — Conditional Presence Care
Offer monitoring/care only when value is demonstrated, with bounded cadence, work, escalation and fees. **Active; legal/pricing approvals remain external.**

## D-004 — Single-writer persistence
SQLite and filesystem for local single-writer operation; revisit only if scale demands. **Active.**

## D-005 — Separate web and monitoring worker processes
Supervise monitoring durability separately where the current operator runtime uses workers. **Active where applicable.**

## D-006 — Provider-neutral deployment
Avoid hardcoded external provider dependencies; hosted deployment is deferred. **Historical deployment principle, not immediate work.**

## D-007 — Stripe external authority
External payments and invoices are authoritative; local state is a mirror. **Active data-safety boundary.** Historical Stripe SaaS binding must not be deleted or charged on speculation.

## D-008 — Sensitive data
Never place secrets, MFA, full card details or protected personal/health data in ordinary repo/AI artifacts. **Active.**

## D-009 — Signup vs bootstrap
Previously required production public signup and nonproduction bootstrap. **Superseded for operator-only runtime by D-014**; historical SaaS code and records require preservation safeguards.

## D-010 — Synthetic does not mean real readiness
Synthetic acceptance and CI do not authorize outreach, billing, or claims of real-client readiness. **Active hard gate.**

## D-011 — Initial market/vertical
Historical Ireland-first dental focus. **Historical, not a hard constraint** on current Webify prospecting; no implied authorization to contact prospects.

## D-012 — Dual-runtime SaaS architecture
Former decision: operator plus hosted multi-tenant SaaS. **Superseded as active development direction by D-014**; retain as historical rationale only.

## D-013 — Local-first commercial SaaS
Former decision: local SaaS-capable production environment before hosting. **Superseded as active development direction by D-014**.

## D-014 — Operator-only focus and evidence-gated post-merge acceptance
**Status: active.** Operator-centric simplification merged under #399. Reconcile code/docs, inspect TRON installation, run full preflight and execute controlled end-to-end operator acceptance. Merged and CI-green are distinct from TRON acceptance. No unsolicited outreach, payment processing, destructive migration or production-data ingestion without approval.
