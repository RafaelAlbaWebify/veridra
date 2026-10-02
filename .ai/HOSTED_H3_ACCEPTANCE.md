# Hosted H3 report polish acceptance

Status: **COMPLETE**
Prepared: 2026-10-02

## Scope

H3 improves professional report output without replacing the existing evidence engine, PDF renderer or tenant report-profile persistence.

## Implemented

- branded cover retained;
- navigable report table of contents;
- assessment overview with bounded Passed / Attention / Unavailable distribution;
- stable section anchors;
- improved print flow for long reports;
- findings section starts on a fresh PDF page;
- saved reusable report profiles retained as the persistence model;
- server-side section presets: Full, Executive and Technical;
- presets are CSP-compatible and require no client-side JavaScript;
- HTML preview remains the source rendered to PDF;
- real Chromium PDF smoke covers the polished report HTML;
- existing page-number/footer behavior remains unchanged.

## Preset semantics

- Full: all supported report sections;
- Executive: executive summary, priorities, business-impact view, roadmap, conclusion and CTA;
- Technical: executive summary, assessment areas, findings, roadmap and conclusion;
- Custom: saved checkbox section order.

Preset selection changes sections only. Branding, profile identity, selected assessment areas, evidence policy and client metadata remain independent.

## Preserved boundaries

H3 does not:

- invent a synthetic website score;
- add unobserved charts or metrics;
- introduce another report-profile store;
- fetch remote branding assets;
- weaken report entitlement checks;
- loosen CSP to run inline preset JavaScript;
- change the evidence collection contract.

## Existing capability deliberately reused

- Playwright PDF renderer;
- report footer page numbers;
- reusable tenant report profiles;
- existing cover/logo/contact/CTA fields;
- executive summary, priority, business-impact, roadmap, assessment-area and evidence sections;
- English/Spanish customer-facing localization.

## Closure evidence

Final baseline:

- code head: `09cf905f`;
- GitHub Actions run: `37001235636`;
- result: **success**;
- Ruff: passed;
- strict mypy: passed;
- pytest: passed;
- deterministic audit: passed;
- discovery acceptance: passed;
- Windows portability: passed;
- sales-contract Playwright: passed;
- full operator Playwright acceptance: passed.

## Next phase

**H4 — Audit scale / job model**

Use the existing durable monitoring-job design as the architectural pattern:

1. asynchronous crawl/audit job state;
2. tenant/project qualified ownership;
3. transactional leasing and retries;
4. progress fields appropriate to crawl work;
5. page-budget/concurrency enforcement;
6. measured 500-page workload before raising supported large-crawl limits.

Do not merely raise `crawl_profiles.py` hard caps.
