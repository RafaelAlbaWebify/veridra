# Phase C Reduced Operator Review — Run #27

Status: operator/human review aid only.  
Source: SMB Real Validation #27 / run `35894403715` / commit `ba7dd173389a69dfe67b7e613f3c0b7fb4e7243b`.  
No outreach. Public evidence only.

## Purpose

Do **not** re-review all 202 attention findings.

For each evidence-sufficient business:

1. start a timer;
2. confirm 2–3 high-value findings below against the public site/evidence;
3. scan briefly for one material issue VERIDRA may have missed;
4. record any false positive that would change the business-level value/qualification decision;
5. stop the timer and record total validation minutes.

Generic header hygiene, cookie flags, homepage trust exposure, sitemap-in-robots and other monitor-only items do not need manual commercial validation.

## Review set

| Business | Evidence | Mechanical commercial findings | Confirm first | Known material miss to count |
|---|---|---:|---|---|
| Dublin City Dentist | sufficient / 10 HTML pages | 6 | accessibility.interactive-names; content.placeholder-default; local.location-route | literal `call phone number` placeholder |
| Crown Dental Dublin | sufficient / 10 | 5 | accessibility.form-labels; accessibility.interactive-names; content.opening-hours-consistency | none currently recorded beyond validated Crown hours finding |
| MB Dental | sufficient / 10 | 10 | accessibility.interactive-names; crawl.description; next highest-value remaining item | current public Contact → Treatments navigation works; record run #27 broken-link claim as non-material/currently non-reproducible |
| G-Dental | sufficient / 5 | 7 | ai.open-graph-description; ai.open-graph-title; crawl.canonical | none currently recorded |
| Ballincollig Dental Practice | sufficient / 10 | 6 | accessibility.interactive-names; ai.open-graph-description; ai.open-graph-title | conflicting opening-hour sets on Contact page |
| Shandon Dental | sufficient / 10 | 6 | accessibility.form-labels; accessibility.interactive-names; crawl.description | stale dated oral-cancer screening promotion |
| Elmwood Dental & Facial Aesthetics | sufficient / 10 | 10 | accessibility.form-labels; accessibility.interactive-names; security.insecure-resources | materially different opening-hour schedules across pages |
| Clontarf Dental Practice | sufficient / 10 | 7 | accessibility.form-labels; accessibility.interactive-names; security.insecure-resources | none currently recorded |
| Fiacla Dental | sufficient / 4 | 9 | accessibility.interactive-names; ai.open-graph-description; ai.open-graph-title | demo contact values alongside real clinic details |
| Dublin Orthodontist | sufficient / 10 | 6 | accessibility.interactive-names; ai.open-graph-description; ai.open-graph-title | none currently recorded after Office Hours correction |
| Macroom Dental Practice | sufficient / 8 | 9 | accessibility.form-labels; accessibility.interactive-names; crawl.description | none currently recorded |
| South Dublin Dental | **insufficient / 0 HTML pages** | n/a | **do not qualify from this run** | acquisition/evidence volatility; rerun or independent evidence required |

## Stop rule

Analyzer calibration is frozen. Do not reopen it for wording, generic hygiene or non-material coverage gaps.

Reopen only when a demonstrated false positive/false negative:
- changes the business-level opportunity/qualification decision; or
- makes VERIDRA's evidence claim materially false.

## Required operator output per evaluable business

Record only:

- `validation_minutes`
- `confirmed_high_value_findings`
- `material_false_positive_count`
- `material_miss_count`
- `material_miss_notes`
- `owner_understandable` = yes/no
- `commercial_value_present` = yes/no
- `webify_remediable_value_present` = yes/no
- `business_review_complete` = yes/no

The goal is to measure qualification/value reliability, not to perfect every analyzer.


## Creator / provider context

For each reviewed website, if public attribution exists, record separately:

- creator / agency / provider name;
- public attribution source (footer, credits, case study, etc.);
- client-site last-updated label if visible;
- creator/provider current positioning and services;
- obvious contradictions between provider claims and observed client-site condition.

This context is useful for competitor intelligence and future VERIDRA analysis, but **must not be included in operator validation minutes** and must not reopen #297 analyzer calibration unless it materially changes the qualification/evidence claim.


## Conversion / commercial journey

For each reviewed business, add when observable:

- Primary CTA
- Secondary CTA
- Booking
- Form
- Chatbot / live chat
- CRM / provider detectable
- Contact alternatives
- Journey tested
- Friction
- Broken / dead routes
- Automation visible
- What VERIDRA detects
- What VERIDRA misses
- Candidate future finding
- Value if detected automatically: low / medium / high
- Frequency: unknown until sample aggregation

Provisional maturity levels for human validation only:

- Level 0 — no clear conversion path
- Level 1 — phone / email / contact form
- Level 2 — structured enquiry or booking
- Level 3 — booking + chatbot / CRM / lead capture
- Level 4 — connected acquisition system with booking + CRM + automation + follow-up + tracking

Do not turn these into VERIDRA scoring or implementation requirements during #297. Aggregate after the sample and promote only patterns that are frequent + valuable + automatable, or frequent + valuable + suitable for AI/human interpretation.
