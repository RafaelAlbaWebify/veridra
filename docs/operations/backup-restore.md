# Production backup and restore

Veridra's durable state spans an identity SQLite database and tenant filesystem state. The tenant root also contains the durable monitoring-job SQLite database. These stores do not share one transaction boundary.

For that reason, `veridra-backup` deliberately does **not** claim a live cross-store atomic snapshot.

## Consistency rule

Before backup or restore, stop or otherwise quiesce every writer that can change durable state:

- the Veridra web process;
- scheduled/running `veridra-monitoring-worker` processes;
- Stripe webhook delivery or any other billing integration that can project subscription state;
- manual maintenance commands that write identity or tenant data.

The CLI requires `--confirm-quiesced` as an explicit operator assertion. The flag cannot prove that processes are stopped; operational supervision must enforce it.

## What a snapshot contains

A snapshot contains:

- a SQLite-online-backup copy of `VERIDRA_IDENTITY_DB`;
- the adjacent `identity-email-deliveries/` evidence directory when present;
- the complete `VERIDRA_TENANT_DATA_ROOT`, including tenant projects, assessments, reports, leads, tasks, workspace policy/usage, Stripe binding/subscription evidence and `monitoring-jobs.sqlite3`;
- `manifest.json`, containing the backup format version, Veridra version, UTC creation time, consistency declaration, file sizes and SHA-256 digests.

The manifest uses archive-relative names only. Absolute production filesystem paths and runtime environment variables are not written into it.

Runtime secrets are not separately exported. A secret is present only if an operator has incorrectly stored it inside one of the durable source directories; production secrets should remain in the external secret store.

## Create a backup

With the normal production environment variables configured:

```text
veridra-backup backup \
  --output /secure-backups/veridra-2026-08-20.zip \
  --confirm-quiesced
```

Or provide `--identity-db` and `--tenant-data-root` explicitly.

The command refuses to:

- run without the quiescence assertion;
- overwrite an existing archive;
- place the archive inside the identity or tenant durable source directories;
- follow symbolic links inside durable data;
- snapshot an identity SQLite database that fails `PRAGMA quick_check`.

The output archive is written through a temporary file and published only after creation succeeds.

After backup, move/copy the archive to storage with independent durability and access control. Keeping the only backup on the same disk or volume as production is not sufficient.

## Restore a backup

Restore into empty durable targets by default:

```text
veridra-backup restore \
  --archive /secure-backups/veridra-2026-08-20.zip \
  --confirm-quiesced
```

The restore verifies before writing production targets:

- ZIP structure and safe relative paths;
- exact manifest membership (no undeclared files or duplicate paths);
- every file size and SHA-256 digest;
- supported snapshot format version;
- restored identity SQLite integrity.

If durable targets already contain state, restore refuses by default. Replacement requires the additional explicit option:

```text
--replace-existing
```

Use replacement only during a controlled recovery after preserving the current state separately.

## Recovery validation

After a restore:

1. Keep external writers stopped.
2. Start one web process.
3. Require `GET /health/live` = `200`.
4. Require `GET /health/ready` = `200`.
5. Validate browser sign-in with a controlled account.
6. Validate a representative tenant project/report and monitoring history.
7. Run the normal commercial acceptance/deployment checks.
8. Confirm Stripe binding/subscription evidence is consistent with the current provider state before accepting new billing webhooks.
9. Resume the monitoring worker and external billing delivery only after validation succeeds.

## Retention and verification

A production schedule should keep multiple generations and periodically restore one into an isolated environment. Archive creation alone is not proof of recoverability.

At minimum, monitor and record:

- backup command exit status;
- resulting archive path and size;
- snapshot creation timestamp;
- restore-test date and result;
- the deployed Veridra commit associated with the snapshot.

Do not log archive contents, authentication records, personal data or secret values as part of backup telemetry.
