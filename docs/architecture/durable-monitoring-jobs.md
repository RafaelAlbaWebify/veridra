# Durable tenant monitoring jobs

## Purpose

This milestone introduces a durable local job foundation for scheduled tenant monitoring without embedding an infinite worker loop inside the web process.

## Security boundary

Every job is qualified by both `tenant_id` and `project_id`. API callers may enqueue, list or cancel jobs only after the existing authenticated tenant and capability checks succeed. Worker execution must reload the tenant project before running and must write assessments and delivery attempts only through tenant-qualified stores.

## Job lifecycle

Jobs use explicit states:

- `queued`: eligible when `next_attempt_at` is due;
- `leased`: owned temporarily by one worker until `lease_expires_at`;
- `succeeded`: terminal successful execution;
- `failed`: terminal after the configured retry limit;
- `cancelled`: terminal administrative cancellation.

A failed attempt that still has retries remaining returns the job to `queued`, increments the attempt counter, records the last error and sets a future `next_attempt_at`.

## Idempotency

Enqueue uses a deterministic key derived from tenant, project and logical run window. Re-enqueueing the same logical run must return the existing job rather than creating duplicate monitoring work.

## Leasing

Lease acquisition is transactional. Only one worker can transition a due queued job to leased. Expired leases may be recovered by another worker. Completion and failure operations must verify the current lease owner.

## Worker boundary

The first implementation is a narrow command-line worker that leases and executes a bounded number of jobs, then exits. Process supervision and scheduling belong to deployment tooling, not the web application.

## Explicit exclusions

- Redis, SQS, Celery or other distributed queue infrastructure;
- multi-region coordination;
- production SMTP configuration;
- billing and quota enforcement;
- deployment orchestration.

Related to issue #83.
