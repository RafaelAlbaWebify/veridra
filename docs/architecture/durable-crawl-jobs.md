# Durable tenant crawl jobs

## Purpose

H4 moves potentially long crawl work out of long-lived HTTP requests while preserving VERIDRA's tenant isolation, bounded evidence, usage accounting and single-host persistence model.

The implementation deliberately follows the established durable monitoring-job pattern rather than introducing a second queue technology.

## Current product limit

The customer-facing named crawl profiles remain:

- Quick — 10 pages;
- Standard — 25 pages;
- Deep — 100 pages.

H4 does **not** raise those product limits.

A deterministic 500-page workload is proven separately at engine and worker level so larger commercial limits can be considered later from evidence rather than by merely increasing hard caps.

## Durable job state

Crawl jobs persist in SQLite with explicit states:

- `queued`;
- `leased`;
- `succeeded`;
- `failed`;
- `cancelled`.

Each job records:

- tenant and project identifiers;
- target URL;
- crawl-profile label;
- reserved page budget;
- pages completed;
- idempotency key;
- retry state;
- lease expiry;
- persisted assessment identifier;
- audit/page reservation identifiers;
- timestamps and last error.

## Isolation and idempotency

Job identifiers and idempotency keys include tenant, project, target, profile, page budget and request key.

API access remains tenant-qualified. Worker execution reloads tenant project state and rejects target/profile/page-budget drift before writing an assessment.

Repeated enqueue of the same logical request returns the existing job without double-reserving usage.

## Leasing and retry

Workers lease due work transactionally.

A lease has:

- one worker token;
- explicit expiry;
- retry count;
- retry scheduling.

Progress updates are lease-bound and can extend the lease while work is still advancing. A stale worker cannot continue updating a lease recovered by another worker.

If assessment persistence succeeds but later metering is interrupted, the assessment identifier is retained so a retry can reconcile accounting without recrawling.

## Progress

`crawl_site()` accepts a progress callback and reports each successfully included HTML page.

The durable worker persists `pages_completed` through the active lease. Progress cannot exceed the job's reserved page budget.

## Usage accounting

The enqueue path reserves:

- one audit;
- the job page budget.

On success the worker records:

- one audit;
- the actual crawled-page count.

Unused reserved page capacity is released by reservation reconciliation. Terminal failures release remaining reservations. Cancellation releases queued/leased reservations from the API boundary.

## Concurrency

Plan policy contains `max_concurrent_crawl_jobs`.

The job store enforces tenant-scoped active-job concurrency transactionally before insert. Idempotent duplicate requests are resolved before the concurrency check.

Current concurrency values are plan-defined and do not imply horizontal/multi-host execution.

## Worker process

`CrawlWorker` leases a bounded number of jobs and exits.

`crawl_worker_cli.py` exposes the bounded CLI execution path.

Process supervision belongs to deployment tooling. H7 must prove the actual hosted scheduler/supervision setup.

## 500-page scale evidence

Two deterministic no-network tests prove the scale boundary without changing customer-facing limits:

1. `tests/test_crawl_scale.py`
   - same-origin sitemap;
   - 500 HTML pages;
   - bounded bytes/time/sitemap limits;
   - 500 progress callbacks;
   - no blocked/failed/skipped pages.

2. `tests/test_crawl_worker_scale.py`
   - durable job page budget = 500;
   - worker leases the job outside HTTP;
   - real `crawl_site()` processes 500 pages;
   - 500 progress updates remain lease-bound;
   - terminal state = succeeded.

The closure run passed on Linux and Windows/operator acceptance.

## Explicit exclusions

H4 does not:

- expose a 500-page product profile;
- introduce Redis/Celery/SQS;
- add horizontal workers;
- make web requests execute 500-page crawls synchronously;
- establish production worker supervision;
- decide final plan pricing or page allowances.

Those remain later product/deployment decisions.
