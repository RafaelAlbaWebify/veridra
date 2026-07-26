# Durable monitoring worker operations

## Purpose

`veridra-monitoring-worker` leases and executes a bounded number of due tenant-monitoring jobs, then exits. It is intentionally not an infinite in-process thread and does not schedule itself.

## Required configuration

Set the tenant data root through either:

```text
VERIDRA_TENANT_DATA_ROOT=/absolute/path/to/tenant-data
```

or the command-line option:

```text
veridra-monitoring-worker --tenant-data-root /absolute/path/to/tenant-data
```

The worker and web application must use the same tenant data root. The durable queue database is stored at:

```text
<tenant-data-root>/monitoring-jobs.sqlite3
```

## Running a bounded worker pass

```text
veridra-monitoring-worker --limit 10
```

The command reports how many jobs were leased, succeeded, returned for retry, or reached terminal failure. `--limit` must remain between 1 and 100.

Run the command from an external supervisor such as a systemd timer, Windows Task Scheduler, container cron replacement, or a managed job runner. Deployment supervision is outside the web application.

## Job lifecycle

- `queued`: eligible after `next_attempt_at`.
- `leased`: temporarily owned by one worker token until lease expiry.
- `succeeded`: terminal successful execution.
- `failed`: terminal after the configured attempt limit.
- `cancelled`: terminal administrative cancellation.

A worker crash leaves the job leased until `lease_expires_at`. A later worker can recover that stale lease. Completion and failure require the current opaque lease token; an earlier worker cannot finish a recovered job.

## Retry and idempotency behavior

Enqueueing is idempotent for one tenant, project and logical run window. Repeating the same enqueue request returns the existing job.

A failed attempt records the error and either:

- returns the job to `queued` with a future retry time; or
- marks it `failed` when the attempt limit is reached.

A successful or cancelled job is never leased again.

## Tenant boundary

Every job contains a tenant ID and project ID. The API validates the project inside the authenticated tenant before enqueueing. Worker execution reloads that tenant-qualified project and writes assessments and delivery attempts only beneath the same tenant root.

The worker does not accept tenant IDs, project definitions, targets or roles from untrusted HTTP input during execution. Those values come from the durable job and are revalidated against tenant-qualified project storage.

## Operational checks

Before enabling a recurring supervisor:

1. Confirm the web application and worker use the same absolute tenant-data root.
2. Enqueue one test job through the authenticated API.
3. Run the worker with `--limit 1`.
4. Confirm the job becomes `succeeded` or records a bounded retry error.
5. Confirm the assessment exists beneath the expected tenant/project directory.
6. Confirm no global legacy history directory was written by the worker.

Back up the SQLite queue database and tenant data together when a consistent operational snapshot is required.

## Explicit exclusions

This implementation does not provide Redis, SQS, Celery, multi-region coordination, production process supervision, SMTP configuration, billing quotas or deployment orchestration.
