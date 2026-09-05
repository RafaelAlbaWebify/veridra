# VERIDRA AI Bootstrap Context

## Purpose
VERIDRA is Webify's agency platform for evidence-backed website assessment, prospect qualification, branded reporting, remediation workflow, monitoring and proof of improvement. Webify sells the service outcome; VERIDRA is the internal/agency operating platform.

## Target customer / direction
Initial commercial focus: English-speaking SMB markets, with independent dental practices as the first controlled vertical. Current Presence Care working model is recurring-first and intentionally bounded. Real outreach is currently blocked.

## Product boundary
VERIDRA is not Semrush, a penetration-testing product, a universal AI-visibility oracle, or a proprietary keyword/backlink/traffic database. Findings are bounded public observations and must not be overstated.

Core evidence chain:
`Observation -> evidence -> affected URLs -> business impact -> recommended fix -> task -> rescan verification`

## Major capabilities already implemented
- bounded public website assessment and crawling;
- SEO/AI-readiness/crawler-policy/trust/accessibility/passive-security evidence;
- authenticated multi-tenant agency workflow;
- signup, verification, password recovery, invitations and sessions;
- prospects/leads/projects/deals/proposals/change requests/customer lifecycle;
- branded HTML/PDF/evidence reporting;
- remediation tasks and comparison/rescan workflows;
- durable monitoring worker;
- entitlement/subscription authority and optional Stripe adapter;
- production preflight/deployment-check CLIs;
- backup/restore, ops checks, access logging and tenant offboarding;
- Windows operator launcher and Playwright acceptance flows.

## Critical architectural constraints
- Python >=3.11, FastAPI, Playwright, SQLite + filesystem tenant state.
- Treat persistence as single-writer unless redesigned and tested.
- Web and monitoring worker are separate supervised processes in production.
- Production must use durable identity/tenant paths, trusted HTTPS origin, trusted hosts, SMTP and external secrets.
- VERIDRA stores operational billing references; it is not the company accounting ledger.
- Never store customer passwords, MFA secrets, full card data, PHI or other prohibited sensitive data in ordinary VERIDRA fields, Docs, GitHub or unapproved AI tools.
- Production customer registration is `/signup`; `/onboarding` is non-production bootstrap only.

## Current milestone
P0 real-world first-customer readiness, tracked by GitHub #296 under master gate #284.

**Hard rule: REAL OUTREACH COUNT = 0 until #296 passes and Rafael explicitly approves #284 again.**

## Major blockers
- no verified public production deployment;
- real SMTP provider/sender not yet externally proven;
- Stripe test-mode resources/lifecycle not yet externally proven;
- production invoice/accounting path not yet exercised;
- legal/customer paperwork not production-approved;
- full external dry run not completed;
- human operator acceptance on actual deployed providers not completed.

## Read first
1. `.ai/PROJECT_STATE.json`
2. `.ai/KNOWN_ISSUES.md`
3. `.ai/OPERABILITY.md`
4. `.ai/ROADMAP.md`
5. `.ai/TEST_STATUS.json`
6. `README.md`
7. `docs/operations/production-deployment.md` and related ops docs for deployment work.

Do not rely on old chat claims of readiness. Verify code/tests/runtime evidence using the precedence rules in `SESSION_PROTOCOL.md`.