# Local commercial runtime

## Purpose

This is the current deployment target for the VERIDRA agency/commercial product.

It runs the `VERIDRA_ENV=production` feature set locally on Rafael's Windows PC without a VPS, public DNS, Caddy or external application server.

Public hosting remains a future optional phase.

## Separation from Webify operator

The two local products remain separate.

### Webify operator

- launcher: `VERIDRA_OPERATOR_START.bat`;
- default URL: `http://127.0.0.1:8010/agency`;
- state: `%LOCALAPPDATA%\Veridra`;
- private Webify prospect/customer/Presence Care workflow.

### Commercial agency product

- launcher: `VERIDRA_COMMERCIAL_OPEN.bat`;
- default URL: `http://127.0.0.1:8011/signup`;
- state: `%LOCALAPPDATA%\VeridraCommercial`;
- signup/workspaces/plans/projects/reports/leads/team/commercial monitoring.

The two runtimes must not share identity or tenant state.

## Security boundary

The commercial runtime uses `VERIDRA_ENV=production`.

HTTP is permitted only because both:

- bind host = `127.0.0.1`;
- trusted origin = explicit loopback `http://127.0.0.1:<port>`.

Any future non-loopback production deployment still requires HTTPS.

The launcher never binds `0.0.0.0`.

## Processes

The supported local commercial launcher supervises:

1. web runtime — `python -m veridra.runtime`;
2. recurring monitoring service;
3. durable crawl worker service.

The crawl worker polls the durable crawl-job queue with bounded interval and per-tick job limit.

## Commands

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

List commercial workspaces and copy the Tenant ID needed by provider evidence commands:

```bat
VERIDRA_COMMERCIAL_TENANTS.bat
```

The listing is read-only and shows only tenant ID, workspace name, plan and status; it does not expose credentials or sessions.

A local production preflight may return warnings when optional/public-only configuration is absent.

For the current local phase:

- Legal URLs absent: warning;
- SMTP absent: warning;
- Stripe absent: warning unless explicitly required.

Storage/runtime failures remain critical.

## First use

Open the commercial runtime and create the first commercial workspace through `/signup`.

Do not bootstrap it with the operator-only owner bootstrap.

The commercial and operator identity databases are intentionally separate.

## Backup

Create a quiesced commercial backup:

```bat
VERIDRA_COMMERCIAL_BACKUP.bat
```

Commercial backups are stored under:

`%LOCALAPPDATA%\VeridraCommercial\backups`

The backup pauses all three managed processes before snapshot creation and restarts them afterward.

Keep an independent operator-controlled second copy as part of local acceptance.

## Recovery test

Use:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\windows\veridra-commercial-local.ps1 recovery-test
```

or provide a specific archive with `-BackupPath`.

The recovery test restores into an isolated directory and runs SQLite integrity checks. It must not overwrite active commercial state.

## H-500 local commercial human acceptance

Repository/Playwright acceptance is necessary but does not prove the actual Windows production-local runtime.

After H-400 provider acceptance is complete, start an H-500 operator session with:

```bat
VERIDRA_COMMERCIAL_H500_ACCEPTANCE.bat
```

The launcher:

- records the repository branch/commit and workstation identity;
- runs the supported commercial production preflight;
- starts the supervised web, monitoring and crawl-worker processes;
- captures process status evidence;
- opens the loopback commercial product;
- creates a human checklist covering project/audit, report/PDF, embedded leads, lead management, remediation, monitoring, restart/persistence, backup/independent copy/recovery and provider reconciliation.

The checklist must be exercised personally with synthetic/internal acceptance data. The existing `VERIDRA_COMMERCIAL_ACCEPTANCE.bat` remains an isolated automated regression runner and does **not** satisfy H-500 by itself.

## Stripe test-mode acceptance

Stripe is optional until paid-plan testing begins.

The local H6 flow uses the official Stripe CLI directly from this PC. Stripe can forward signed test events to VERIDRA over loopback; no public VERIDRA server or tunnel is required.

### 1. Authenticate Stripe CLI

Run the official Stripe CLI login flow:

```powershell
stripe login
```

### 2. Configure VERIDRA test billing

Run:

```bat
VERIDRA_COMMERCIAL_STRIPE_CONFIG.bat
```

Enter:

- Solo Price ID;
- Professional Price ID;
- Agency Price ID;
- Stripe test secret key (`sk_test_...`).

The launcher obtains the current Stripe CLI webhook signing secret automatically with `stripe listen --print-secret`.

Storage boundary:

- Price IDs: `%LOCALAPPDATA%\VeridraCommercial\config\stripe.json`;
- Stripe API secret: Windows-user encrypted file;
- webhook signing secret: Windows-user encrypted file;
- no provider secret is stored in the repository.

Restart VERIDRA after changing Stripe configuration:

```bat
VERIDRA_COMMERCIAL_STOP.bat
VERIDRA_COMMERCIAL_START.bat
```

### 3. Verify provider configuration

Run:

```bat
VERIDRA_COMMERCIAL_PROVIDER_PREFLIGHT.bat
```

This contacts Stripe in test mode, verifies all three Price IDs are active recurring test Prices, and writes secret-free JSON evidence into Downloads.

### 4. Start local webhook forwarding

In a separate terminal:

```bat
VERIDRA_COMMERCIAL_STRIPE_LISTEN.bat
```

The launcher verifies that the current Stripe CLI signing secret matches VERIDRA's encrypted configured secret, then forwards the required test events to:

`http://127.0.0.1:8011/api/billing/stripe/webhook`

Keep this listener window open during Checkout, Portal, plan-transition, failure/recovery and cancellation acceptance.

### 5. Clear test billing configuration

If required:

```bat
VERIDRA_COMMERCIAL_STRIPE_CLEAR.bat
```

This removes the local encrypted Stripe configuration. It does not modify Stripe objects in the provider account.

H6 / H-400 provider acceptance is complete. Fresh local-commercial Stripe sandbox phases 0–6 were accepted on 2026-10-03 and are recorded in `docs/operations/hosted-provider-acceptance.md`. Do not repeat that lifecycle merely to satisfy H-500; use read-only provider reconciliation unless new provider drift needs investigation.

## SMTP

SMTP is optional unless automated email is enabled.

If disabled, record it as disabled rather than treating it as a failed local acceptance requirement.

## Future public hosting

The retained `deployment/` bundle, Caddy configuration and public-host documentation are future-use artifacts.

They are not part of the current local commercial operability gate.

If public/customer remote access later becomes necessary, that work must receive a separate deployment and security acceptance.
