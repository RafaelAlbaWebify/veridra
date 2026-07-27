# Veridra product strategy and roadmap

## Working position

> Veridra helps agencies find website risks and growth opportunities, turn them into branded client reports and remediation work, and prove improvements through recurring monitoring.

Expanded:

> Veridra audits technical SEO, AI readiness, trust, accessibility and passive security; captures audit leads; produces evidence-backed white-label reports; converts findings into work; and monitors the results.

## Strategic category

Veridra is a website-audit, evidence, lead-generation, remediation and monitoring platform for:

- web agencies;
- technical consultants;
- MSPs;
- website-maintenance providers;
- hosting and digital-service businesses.

It should borrow proven workflow patterns from established platforms without attempting to reproduce proprietary market-scale datasets.

## Core commercial loop

1. capture a prospect or create a client project;
2. run a bounded multi-page website assessment;
3. produce an evidence-backed white-label report;
4. convert findings into prioritized remediation work;
5. assign, track and verify tasks;
6. rescan the website;
7. demonstrate improvement;
8. convert the work into recurring monitoring or maintenance.

## Evidence model

Every actionable conclusion should follow:

> Observation → evidence → affected URLs → business impact → recommended fix → task → rescan verification.

Scores are acceptable only when every component is explicit, explainable and traceable to findings.

## Differentiation

Veridra should strengthen transparent first-party evidence in:

- technical SEO fundamentals;
- indexability and crawlability;
- AI crawler policy;
- AI technical readiness;
- entity and business clarity;
- structured data;
- passive public security posture;
- domain and email posture;
- accessibility heuristics;
- trust and legal signals;
- contact and conversion routes;
- per-page evidence and affected URL lists;
- remediation tasks;
- monitoring and before/after proof.

## Product patterns to borrow

- project-centric navigation;
- persistent client workspaces;
- clear separation between quick audits and monitored projects;
- prioritized recommendations;
- historical comparisons;
- technical competitor comparisons;
- scheduled reports;
- client-facing dashboards or secure report links;
- evidence-backed AI summaries;
- provider-neutral external-data integrations;
- visible usage and entitlement limits.

## Internal-build exclusions

Do not build internally:

- proprietary keyword databases;
- search-volume estimation;
- backlink crawlers or backlink indexes;
- competitor traffic estimation;
- global rank-tracking infrastructure;
- paid-search intelligence;
- generic AI article writing;
- market-scale AI-prompt databases;
- opaque universal website, authority, credibility or AI-visibility scores.

These require licensed data, enormous crawling infrastructure or claims that would not be defensible from Veridra's first-party evidence.

## AI terminology boundary

Keep separate:

- **AI technical readiness:** whether content is accessible, structured, identifiable and technically understandable;
- **AI crawler policy:** whether named crawlers are allowed or blocked;
- **sampled AI visibility:** whether selected AI providers mention or cite the business for a controlled set of prompts.

Robots.txt, structured data and extractability checks are not proof of actual AI visibility.

Any future sampled AI-visibility feature must:

- execute real external prompts;
- store provider, model, prompt, response and timestamp;
- use a bounded, reviewable prompt set;
- label results as sampled observations;
- avoid claims of complete coverage.

## Roadmap sequence

### 1. Completed foundations

- authentication and tenant isolation;
- tenant-qualified projects and operational data;
- white-label report profiles and report artifacts;
- durable monitoring jobs and bounded worker execution;
- production runtime hardening and deployment guidance.

### 2. Current priority: agency workflow review

Review the complete journey from the perspective of a non-technical agency operator:

1. agency onboarding;
2. workspace setup;
3. client project creation;
4. crawl-profile selection;
5. audit execution;
6. finding review;
7. report-profile configuration;
8. PDF/report generation;
9. report delivery;
10. lead capture;
11. lead-to-project conversion;
12. task creation;
13. monitoring scheduling;
14. rescan and comparison;
15. team permissions and audit trail.

The existence of routes or modules is not proof that the commercial workflow is understandable or usable.

### 3. Next major product feature

Technical competitor comparison based only on observable website evidence.

Requirements:

- bounded number of domains;
- same crawl profile;
- same assessment time window;
- comparison of crawlability, indexability, metadata, broken links, structured data, trust, accessibility heuristics, passive security, AI crawler policy, business identity, contact routes and page-quality findings;
- no traffic, keyword, authority, backlink or ranking claims unless supplied by an explicitly named external provider.

### 4. External integrations

Use a provider-neutral architecture and prioritize customer-owned first-party data:

1. Google Search Console;
2. Google Analytics 4;
3. PageSpeed Insights or CrUX;
4. Bing Webmaster Tools;
5. Google Business Profile when commercially justified.

Only later consider a limited commercial SEO-data provider for top organic keywords, basic ranking observations, limited competitor discovery, backlink summaries and branded-versus-non-branded visibility.

Every external metric must retain:

- provider;
- collection timestamp;
- country or database;
- device where applicable;
- freshness;
- limitations;
- usage cost;
- source attribution.

External data must enrich reports without becoming a hidden dependency of the core audit engine.

## Positioning exclusions

Do not market Veridra as:

- a full Semrush alternative;
- a comprehensive SEO-intelligence suite;
- a penetration-testing tool;
- proof of universal AI visibility;
- a replacement for proprietary keyword or backlink data.

## Documentation status vocabulary

Repository and product documentation should distinguish:

- **implemented:** present in the repository;
- **locally verified:** covered by repository tests and audits;
- **production-ready foundation:** has fail-closed application boundaries but still requires deployment infrastructure and environment validation;
- **experimental:** available for evaluation without a production-support claim;
- **intentionally deferred:** excluded by strategy or awaiting a provider/business decision.

## Commercial completion measure

Do not use route count or module count as the primary measure of readiness. Measure whether an agency operator can complete the full revenue workflow without hidden technical intervention:

> prospect/client → audit → evidence → branded report → remediation work → rescan proof → recurring monitoring.