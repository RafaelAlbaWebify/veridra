# Production monitoring and alerting

Veridra exposes two different operational layers:

- HTTP liveness/readiness for traffic management: `GET /health/live` and `GET /health/ready`;
- a non-public operator check for scheduled alerting: `veridra-ops-check`.

Do not expose `veridra-ops-check` as a public HTTP endpoint. Run it from the host, container task, scheduler or monitoring agent that already has access to the production durable paths.

## Command

With the normal production environment variables configured:

```text
veridra-ops-check
```

To include backup freshness:

```text
veridra-ops-check --backup-dir /secure-backups
```

Important options:

```text
--recent-hours 24
--queued-overdue-minutes 30
--backup-max-age-hours 26
```

The command writes one compact JSON object to stdout and exits with:

- `0` — all checks are healthy;
- `1` — warning; operator attention is appropriate;
- `2` — critical; investigate promptly.

A scheduler or monitoring platform can alert directly from that exit code and store the JSON result as bounded operational evidence.

## Checks

The command evaluates:

- identity SQLite integrity and the required identity schema;
- tenant-data-root availability;
- monitoring-job SQLite integrity;
- recent terminal monitoring failures;
- queued monitoring jobs that are overdue beyond the configured threshold;
- expired worker leases;
- malformed monitoring timestamps;
- recent failed identity-email deliveries;
- malformed identity-email evidence;
- optional backup freshness.

Backup freshness accepts only ZIP files containing a valid Veridra snapshot manifest with the supported format and `operator_quiesced` consistency declaration. It uses the manifest creation timestamp rather than filesystem modification time.

Freshness is not a full restore/integrity test. `veridra-backup restore` and periodic isolated restoration remain the proof that the complete snapshot is recoverable.

## Privacy boundary

The JSON output intentionally contains only check names, severity, aggregate counts and generic details. It does not emit:

- tenant or project identifiers;
- customer email addresses;
- monitoring error text;
- identity-email provider error text;
- durable filesystem paths;
- secret values.

Keep the output protected as operational telemetry even though it is deliberately bounded.

## Suggested supervision

A practical starting point is to run the operator check every five minutes and alert on non-zero exit codes. Tune thresholds to the actual worker cadence and backup schedule before production launch.

Use separate signals for separate decisions:

- `/health/live`: restart/process-health decision;
- `/health/ready`: route/no-route customer traffic decision;
- `veridra-ops-check`: operator investigation/alert decision.

Do not automatically restart the application merely because the operator check reports a warning or a terminal business job failure.

## Backup alerting

Only configure `--backup-dir` when that directory represents the location in which completed Veridra snapshot archives are expected to appear. If backup creation and off-host upload are separate jobs, monitor both the local snapshot job and the destination storage independently.

A fresh local manifest does not prove the off-host copy succeeded.

## Deployment validation

Before relying on alerts in production:

1. exercise one healthy run and confirm exit `0`;
2. temporarily use a deliberately stale backup test directory and confirm exit `2`;
3. create a controlled overdue monitoring-job fixture in a non-production environment and confirm warning behavior;
4. verify the monitoring platform captures stdout without adding environment-variable dumps;
5. verify alert messages do not attach durable files or sensitive logs;
6. record the monitoring cadence and thresholds with the deployed configuration.
