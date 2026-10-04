# Webify local-agency runtime

## Purpose

This is the current local deployment target for VERIDRA **inside Webify**.

It runs the hardened `VERIDRA_ENV=production` feature set on Rafael's Windows PC with `VERIDRA_LOCAL_AGENCY=1`, bound only to loopback. It is **not a VERIDRA SaaS deployment** and does not require Rafael to sign up for, subscribe to, or administer a separate VERIDRA service.

Public hosting remains optional future work.

## Product model

The local-agency runtime is Webify's private operating console. It combines the useful capabilities that were previously split across the operator and commercial/SaaS experiments:

- prospect discovery and qualification;
- sales/proposals;
- inbound audit leads and embedded lead forms;
- customers and onboarding;
- client projects;
- bounded website audits;
- saved findings and affected-page evidence;
- white-label reports and PDF output;
- remediation tasks;
- monitoring/comparison;
- Presence Care lifecycle.

The following SaaS concepts are intentionally **not part of normal local operation**:

- public VERIDRA signup;
- browser login for the sole local owner;
- Free/Solo/Professional/Agency subscription selection;
- VERIDRA billing/Stripe Checkout;
- SaaS seat administration;
- plan-based feature locks and monthly SaaS quotas.

Retained hosted/SaaS modules remain in the repository for historical evidence or possible future reuse, but the local runtime does not route through them.

## State boundary

The compatibility launcher continues to use:

`%LOCALAPPDATA%\VeridraCommercial`

This state remains separate from the older operator root:

`%LOCALAPPDATA%\Veridra`

Keeping the roots separate during H-500 avoids a destructive data migration while the unified Webify workflow is being accepted. The word “Commercial” in existing filenames/state paths is therefore a compatibility name, not a statement that VERIDRA remains a SaaS product.

The local-agency runtime resolves the single active local owner directly on loopback. No browser signup/login is required.

## Security boundary

The launcher sets:

- `VERIDRA_ENV=production`;
- `VERIDRA_LOCAL_AGENCY=1`;
- bind host `127.0.0.1`;
- trusted origin `http://127.0.0.1:<port>`.

Local-agency mode is rejected unless it is production-mode and loopback-only. The launcher never binds `0.0.0.0`.

Any future remote/public deployment requires a separate architecture and security acceptance.

## Processes

The supported launcher supervises:

1. web runtime — `python -m veridra.runtime`;
2. recurring monitoring service;
3. durable crawl worker service.

Managed PID files are validated against the expected command line so a Windows PID reused after reboot cannot be mistaken for a VERIDRA process.

## Normal commands

Open/start:

```bat
VERIDRA_COMMERCIAL_OPEN.bat
VERIDRA_COMMERCIAL_START.bat
```

Status:

```bat
VERIDRA_COMMERCIAL_STATUS.bat
```

Stop:

```bat
VERIDRA_COMMERCIAL_STOP.bat
```

Preflight:

```bat
VERIDRA_COMMERCIAL_PREFLIGHT.bat
```

The `VERIDRA_COMMERCIAL_*` names are retained for compatibility. They now launch the Webify private local-agency runtime.

The normal entry point is:

`http://127.0.0.1:8011/`

which redirects to the Webify agency console at `/agency`.

## Preflight expectations

For private local-agency operation:

- hardened runtime configuration: required;
- durable storage: required;
- Terms/Privacy URLs: not required for the private local console;
- SMTP: optional unless an intentional email workflow is enabled;
- VERIDRA SaaS Stripe billing: not required.

A public deployment would have different legal, identity, email, TLS and provider requirements and is not covered by this local acceptance.

## Identity and capabilities

The sole active local owner is resolved automatically only when the request and bind are loopback-local.

Normal local operation does not expose:

- `/signup`;
- `/login`;
- `/plans`;
- `/billing`;
- `/workspace`;
- SaaS team/seat administration.

Plan/usage records created by the historical SaaS work may remain on disk, but they do not gate local Webify features, project capacity, embedded lead forms or local usage.

## Backup

Create a quiesced backup:

```bat
VERIDRA_COMMERCIAL_BACKUP.bat
```

Backups are stored under:

`%LOCALAPPDATA%\VeridraCommercial\backups`

The backup pauses all three managed processes before snapshot creation and restarts them afterward.

Keep an independent operator-controlled second copy as part of H-500.

## Recovery test

Use:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\windows\veridra-commercial-local.ps1 recovery-test
```

or provide a specific archive with `-BackupPath`.

The recovery test restores into an isolated directory and runs SQLite integrity checks. It must not overwrite active Webify local-agency state.

## H-500 human acceptance

Start the real-workstation acceptance session with:

```bat
VERIDRA_COMMERCIAL_H500_ACCEPTANCE.bat
```

The compatibility launcher now validates the **Webify local-agency product**, including:

- loopback preflight and supervision;
- local owner identity without SaaS signup/login;
- unified prospect/sales/inbound-lead/customer/project navigation;
- bounded audits;
- branded report/PDF output;
- embedded lead generation;
- lead conversion;
- remediation and monitoring;
- restart/persistence;
- backup, independent copy and isolated recovery;
- isolation from SaaS plan/billing/provider dependencies;
- Rafael's human usability judgment.

Synthetic/internal acceptance data only. Real outreach remains governed separately by the first-customer/legal gates.

## Historical H6 / H-400 Stripe evidence

The Stripe sandbox lifecycle completed on 2026-10-03 remains valid historical evidence in:

`docs/operations/hosted-provider-acceptance.md`

It proved the former hosted/SaaS billing implementation but is **not a dependency of current Webify local-agency operation**.

Normal local startup clears SaaS Stripe environment variables and does not configure the Stripe billing runtime. Existing encrypted Stripe sandbox configuration can remain on disk without gating startup or features.

Legacy provider snapshot/reconciliation helpers are retained only for historical evidence inspection. The old Stripe listener and H6 phase commands are retired from normal use.

## SMTP

SMTP is optional. If an email notification/report workflow is intentionally enabled, configure and test it explicitly. If disabled, record it as disabled rather than treating its absence as a product failure.

## Future hosting

A hosted/multi-user VERIDRA product may be reconsidered only if a real business need justifies it. That would be a new product/deployment decision with its own identity, billing, privacy, TLS, provider and launch acceptance. It is not the current VERIDRA/Webify architecture.
