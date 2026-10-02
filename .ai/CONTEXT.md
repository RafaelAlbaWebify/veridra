# VERIDRA AI Bootstrap Context

## Purpose

VERIDRA is an evidence-backed digital-presence platform with two deliberately separate product tracks over one shared core.

1. **Webify operator** — `VERIDRA_ENV=operator`
   - private Webify workflow;
   - Windows / loopback;
   - prospect discovery, qualification, proposals, customer delivery and Presence Care;
   - governed by the existing first-customer / no-outreach gates.

2. **Commercial agency product** — `VERIDRA_ENV=production`
   - multi-tenant-capable agency website-audit / white-label / lead-generation product;
   - current deployment target is local Windows / loopback;
   - public internet hosting is deferred and is not a current acceptance gate;
   - not yet commercially accepted.

## Commercial product target

Working position:

**A lower-cost agency website-audit and lead-generation product with broader website credibility coverage.**

Primary commercial workflow:

`signup → workspace/plan → audit/project or lead form → bounded crawl → findings/affected URLs → branded report → lead/client conversion → remediation → reassessment/monitoring`

## Evidence boundary

Core evidence chain:

`Observation → evidence → affected URLs/surfaces → business impact → recommended fix → task → rescan/verification`

VERIDRA may assess bounded public signals for technical SEO, crawl/indexability, AI crawler policy/readiness, trust/business credibility, accessibility heuristics, passive public security/email-domain posture and structured/page-level evidence.

Do not claim:

- penetration testing;
- universal AI visibility;
- backlink/traffic/keyword intelligence VERIDRA does not collect;
- legal/accessibility certification;
- accounting authority.

## Major implemented foundations

- bounded same-origin crawling and public-target safety;
- page-level observations and commercial findings;
- tenant-qualified identity/storage;
- signup, verification, recovery, invitations and sessions;
- Free/Solo/Professional/Agency policy and usage ledger;
- tenant projects and assessment histories;
- white-label report profiles;
- HTML/PDF/evidence reporting;
- remediation/task state;
- recurring monitoring worker and comparisons;
- embedded tenant lead forms;
- lead management and lead-to-project conversion;
- Stripe SaaS adapter;
- backup/restore, deployment and operations tooling;
- Windows operator launcher/acceptance.

Implementation does not prove launch readiness.

## Current architecture decisions

Read `.ai/DECISIONS.md`, especially:

- D-001 bounded evidence;
- D-004 single-writer persistence initially;
- D-005 separate web/worker processes;
- D-007 Stripe authority boundary;
- D-009 signup vs bootstrap onboarding;
- D-010 synthetic lifecycle != real readiness;
- D-012 dual-runtime product architecture.

Current commercial deployment is local single-machine / loopback. The single-host public deployment bundle is retained for future use. Horizontal/multi-node deployment remains deferred.

## Current commercial milestone

**H6 — local commercial provider acceptance.**

H0 SaaS resurrection audit, H1 commercial integrity, H2 commercial UX, H3 report polish, H4 audit-scale foundation and H5 lead-generation product polish are complete. H5 closure baseline: CI run 37006643458 / head bf176450.

Authoritative working evidence:

- `.ai/SAAS_RESURRECTION_AUDIT.md`;
- `docs/product/strategy-and-roadmap.md`;
- `docs/operations/local-commercial-runtime.md`;
- `docs/operations/hosted-provider-acceptance.md` (historical filename; current content is local-commercial H6).

Current work is preparing and executing provider acceptance against the local commercial runtime. Existing Stripe/SMTP code and historical operator evidence are not sufficient by themselves. H6 requires fresh local-runtime test-provider evidence for Stripe Checkout/webhooks/plan changes/failure/portal/cancellation/reconciliation. Local webhook forwarding/test tooling is acceptable; a public server is not required. SMTP delivery is required only if SMTP automation is enabled.

## Current operator milestone

The Webify operator track remains under its separate real-world readiness gates (#279/#284/#296).

**REAL OUTREACH COUNT remains 0 until those operator gates pass and Rafael explicitly approves outreach.**

That rule does not constitute hosted SaaS launch approval. Commercial VERIDRA requires a separate acceptance gate.

## Readiness rule

Do not quote one global VERIDRA operability percentage from older files/chats.

Track evidence separately for each product and capability:

1. implemented;
2. regression-tested;
3. integrated in the intended runtime;
4. manually accepted;
5. externally/provider-validated where applicable.

Historical percentages in older operator planning material are not authoritative for the commercial product.

## Major hosted gaps still expected after H0

- commercial plan/pricing decisions;
- entitlement-aware upgrade/locked-feature UX;
- report/PDF polish;
- safe larger-crawl job model beyond current 100-page profile;
- production proxy-aware public abuse/rate-limit design;
- live SMTP proof;
- Stripe test-provider lifecycle proof;
- local commercial runtime provider evidence;
- backup/restore provider reconciliation;
- local human acceptance.

## Critical persistence / backup boundary

Durable hosted state spans identity SQLite plus tenant filesystem state, including monitoring jobs and tenant lead assessment evidence.

Cross-store backup is not live-atomic. Writers must be quiesced for the verified snapshot process. Use independent off-host copies and periodic restore tests.

## Read first

1. `.ai/DECISIONS.md`
2. `.ai/SAAS_RESURRECTION_AUDIT.md`
3. `docs/product/strategy-and-roadmap.md`
4. `README.md`
5. `docs/operations/single-host-deployment.md`
6. `docs/operations/backup-restore.md`
7. operator-specific `.ai/PROJECT_STATE.json`, `.ai/KNOWN_ISSUES.md` and issue gates only when working on the Webify operator track.

Do not rely on old chat claims of readiness. Verify current code, tests, runtime composition and provider evidence.
