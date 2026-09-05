# VERIDRA AI Bootstrap Context

## Purpose
VERIDRA is Webify's agency platform for evidence-backed SMB digital-presence assessment, prospect qualification, branded reporting, remediation workflow, monitoring and proof of improvement. Webify sells the service outcome; VERIDRA is the internal/agency operating platform.

## Target customer / direction
Initial commercial focus: English-speaking SMB markets, with independent dental practices as the first controlled vertical and Ireland as the first controlled market. Current Presence Care working model is recurring-first and intentionally bounded. Real outreach is currently blocked.

## Product boundary
VERIDRA is not Semrush, a penetration-testing product, a universal AI-visibility oracle, or a proprietary keyword/backlink/traffic database. Findings are bounded public observations and must not be overstated.

Core evidence chain:
`Observation -> evidence -> affected URLs/surfaces -> business impact -> recommended fix -> service classification/task -> rescan/verification`

## Critical real-SMB validation rule
Synthetic tests and safe production infrastructure do not prove that Presence Care is valuable to SMBs.

GitHub #297 is a P0 real-SMB digital-presence validation gate under #296/#284. It must prove, using a no-contact Ireland dental cohort, that VERIDRA findings are substantially true, owner-understandable, commercially relevant and Webify-remediable; that material misses are measured; that operator time is bounded; and that 3–5 shadow Presence Care deliveries support an evidence-backed recurring-value decision.

Current #297 evidence:
- `docs/validation/smb-digital-presence-validation.md`;
- `evidence/smb-validation/ie-dental-cohort-v1.csv` — 25 real practices, `no_contact=true`;
- `evidence/smb-validation/ie-dental-manual-ground-truth-seed-v1.csv` — independent manual comparator seed.

Creating the cohort/protocol alone earns no operability credit.

## Major capabilities already implemented
- bounded public website assessment and crawling;
- SEO/AI-readiness/crawler-policy/trust/accessibility/passive-security evidence;
- authenticated multi-tenant agency workflow;
- signup, verification, password recovery, invitations and sessions;
- prospects/leads/projects/deals/proposals/change requests/customer lifecycle;
- branded HTML/PDF/evidence reporting;
- remediation tasks and comparison/rescan workflows;
- durable monitoring worker;
- operational billing references and separate optional VERIDRA SaaS Stripe adapter;
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
- Standard dental Presence Care excludes patient/clinical systems and Article 9 health-data processing.
- Production customer registration is `/signup`; `/onboarding` is non-production bootstrap only.

## Current milestone
P0 real-world first-customer readiness, with **#297 real-SMB value validation + #296 production/provider readiness** under master gate #284.

**Hard rule: REAL OUTREACH COUNT = 0 until #297 and #296 pass and Rafael explicitly approves #284 again.**

## Current weighted operability
39% complete / 61% remaining.
A dedicated 10% weight is reserved for real-SMB digital-presence validation. Infrastructure/provider completion alone can never reach 100%.

## Major blockers
- #297 real-SMB precision/miss/commercial-value/recurring-value validation incomplete;
- no verified public production deployment;
- real SMTP provider/sender not externally proven;
- Stripe sandbox Presence Care lifecycle not externally proven;
- production invoice/accounting path not exercised;
- legal/customer paperwork not production-approved;
- full external dry run not completed;
- human operator acceptance on actual deployed providers not completed.

## Read first
1. `.ai/PROJECT_STATE.json`
2. `.ai/KNOWN_ISSUES.md`
3. `.ai/OPERABILITY.md`
4. `.ai/ROADMAP.md`
5. `.ai/TEST_STATUS.json`
6. `docs/validation/smb-digital-presence-validation.md` for assessment/value work
7. `README.md`
8. `docs/operations/production-deployment.md` and related ops docs for deployment work.

Do not rely on old chat claims of readiness. Verify code/tests/runtime/real-SMB evidence using the precedence rules in `SESSION_PROTOCOL.md`.
