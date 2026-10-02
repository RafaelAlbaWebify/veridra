# Hosted H4 audit scale acceptance

Status: **COMPLETE**
Closed: 2026-10-02

## Scope

H4 establishes the safe scale foundation for larger hosted audits without raising the current customer-facing 100-page Deep profile.

## Closure baseline

- final H4 code head: `b730c7af`;
- GitHub Actions run: `37005555931`;
- result: **success**;
- Ruff: passed;
- strict mypy: passed;
- pytest: passed;
- deterministic audit: passed;
- discovery acceptance: passed;
- Windows portability: passed;
- sales-contract Playwright: passed;
- full operator Playwright acceptance: passed.

## Acceptance matrix

| H4 criterion | Evidence | Result |
| --- | --- | --- |
| Larger crawl work can live outside HTTP | durable crawl-job API/store/worker/CLI; worker 500-page integration test | PASS |
| Explicit job/progress state | queued/leased/succeeded/failed/cancelled + pages_completed + lease expiry + retries | PASS |
| Tenant/project ownership | tenant-qualified API/storage plus project reload/drift checks | PASS |
| Page-budget enforcement | job page_budget, lease-bound progress bounds, reserved crawled-page usage | PASS |
| Concurrency enforcement | plan `max_concurrent_crawl_jobs` + transactional tenant active-job check | PASS |
| Idempotent enqueue | logical request key resolves before concurrency/quota duplication | PASS |
| Retry/accounting safety | persisted assessment reused across metering retry; terminal reservations released | PASS |
| 500-page engine workload | `tests/test_crawl_scale.py` | PASS |
| 500-page durable worker workload | `tests/test_crawl_worker_scale.py` | PASS |

## Scale result

VERIDRA has now proven a deterministic same-origin 500-page workload both:

- directly through the bounded crawler; and
- through the durable crawl worker outside the HTTP request path.

This proves the architecture can process that workload under synthetic deterministic conditions.

It does **not** prove a real public 500-page website, production network behavior, customer UX, or hosted worker supervision.

## Product limit after H4

No customer-facing limit was raised.

Quick / Standard / Deep remain 10 / 25 / 100 pages.

A larger commercial crawl tier should only be exposed after:

- product/pricing decision;
- real hosted worker supervision in H7;
- real-network operational evidence;
- support/runtime cost review.

## Next phase

**H5 — Lead-generation product polish**

Most H5 foundations already exist from H2:

- tenant-bound embed setup;
- allowed-origin handling;
- proxy-aware throttling;
- plan/upgrade guidance;
- lead provenance;
- project-native conversion;
- assessment attribution.

Remaining H5 audit target: visual form branding and any residual attribution/ergonomics gaps.
