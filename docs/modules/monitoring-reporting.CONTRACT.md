# Monitoring & Reporting Contract
Responsibility: branded report generation/delivery, comparison/history and durable recurring monitoring jobs.
Inputs: tenant-qualified project/assessment data, report profile, monitoring schedule.
Outputs: HTML/PDF/evidence artifacts, comparison evidence, queued/leased monitoring jobs and delivery references.
Guarantees: tenant qualification, deterministic evidence linkage, idempotent enqueue/worker leases/retry behavior.
Dependencies: assessment engine, tenant store, worker runtime, SMTP/report delivery when configured.
Failure behavior: stale leases recover; failed jobs are bounded/retryable; delivery failures remain visible.
Constraints: worker is separate supervised production process.
Non-responsibilities: continuous 24/7 human surveillance, arbitrary marketing campaign work.