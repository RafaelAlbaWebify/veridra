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

## Stripe test-mode acceptance

Stripe is optional until paid-plan testing begins.

Provider preflight may use loopback HTTP for the current local commercial phase.

Use:

```bat
VERIDRA_COMMERCIAL_PROVIDER_PREFLIGHT.bat
```

This validates test-mode Price configuration and writes evidence without provider secrets.

Webhook acceptance for the local phase must use supported test/development forwarding into the loopback endpoint. No public VERIDRA server is required.

H6 is not complete until the actual Stripe test lifecycle is exercised against this local commercial runtime.

## SMTP

SMTP is optional unless automated email is enabled.

If disabled, record it as disabled rather than treating it as a failed local acceptance requirement.

## Future public hosting

The retained `deployment/` bundle, Caddy configuration and public-host documentation are future-use artifacts.

They are not part of the current local commercial operability gate.

If public/customer remote access later becomes necessary, that work must receive a separate deployment and security acceptance.
