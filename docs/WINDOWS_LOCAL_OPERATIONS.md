# VERIDRA Windows-local operations

## Canonical operating model

VERIDRA is an **operator-local application**. Rafael's Windows PC is the canonical runtime host for Webify Presence Care.

This is not merely a pre-cloud evaluation workflow. The intended first-customer architecture is:
- Windows-local execution;
- loopback-only binding on `127.0.0.1`;
- no public application hostname;
- no inbound Internet exposure;
- no VPS/PaaS/Kubernetes requirement;
- customers do not directly log in to VERIDRA;
- customer-facing work is delivered through approved channels and artifacts;
- external SaaS is used only where the business workflow genuinely requires it (for example email delivery and Stripe/accounting).

The existing Linux/Hetzner/Caddy deployment material is historical/optional research and is not a readiness gate.

## First setup

From the repository root:

```bat
VERIDRA_SETUP.bat
VERIDRA_CREATE_SHORTCUT.bat
```

Setup creates `.venv`, installs Veridra with development dependencies, installs Playwright Chromium, and creates the local application directories.

## Daily development/local use

- `VERIDRA_OPEN.bat` starts Veridra if required and opens the local browser UI.
- `VERIDRA_START.bat` starts without opening the browser.
- `VERIDRA_STOP.bat`, `VERIDRA_RESTART.bat`, and `VERIDRA_STATUS.bat` control the local process.
- `VERIDRA_TEST.bat` runs Ruff, strict mypy, and pytest.
- `VERIDRA_DIAGNOSTICS.bat` writes a redacted operational summary.

These existing launchers currently use the normal local/development profile. #296 must prove a **hardened operator-local profile distinct from ordinary development mode** before real customer data is handled. Do not re-label development mode as production merely to satisfy the gate.

## Network boundary

The application must remain bound to:

```text
127.0.0.1
```

The local operating model must not:
- bind to `0.0.0.0`;
- expose VERIDRA on the home LAN;
- create router port-forwarding;
- require public DNS/TLS;
- use a public reverse proxy.

Any future direct-customer/SaaS exposure is a separate architecture decision and is outside the first-customer Presence Care model.

## Local data

Application state is stored beneath:

```text
%LOCALAPPDATA%\Veridra\data
```

Runtime PID/log files are stored beneath:

```text
%LOCALAPPDATA%\Veridra\runtime
```

Local backup archives are stored beneath:

```text
%LOCALAPPDATA%\Veridra\backups
```

## Backup and restore

Create a backup:

```bat
VERIDRA_BACKUP.bat
```

Preview a restore:

```bat
VERIDRA_RESTORE.bat -BackupPath "C:\path\VERIDRA_BACKUP_YYYYMMDD_HHMMSS.zip"
```

Apply only after reviewing source and target:

```bat
VERIDRA_RESTORE.bat -BackupPath "C:\path\VERIDRA_BACKUP_YYYYMMDD_HHMMSS.zip" -Apply
```

A pre-restore safety backup is attempted before replacement.

For #296 acceptance, one verified backup must also be copied to an **independent operator-controlled location** outside the live PC data tree, such as an external drive or another deliberately chosen medium. A paid cloud backup service is not mandatory.

At least one copy must be restored into an isolated target and validated. Archive creation alone is not recovery proof.

## Desktop shortcut

`VERIDRA_CREATE_SHORTCUT.bat` creates or replaces `Veridra.lnk` on the current user's Desktop without administrator rights. The shortcut launches `VERIDRA_OPEN.bat` with the repository root as its working directory.

## #296 acceptance boundary

Before first real customer operation, prove on the actual target workstation:
- hardened local operator profile;
- loopback-only network binding;
- durable identity and tenant state;
- web + monitoring process start/status/restart behavior;
- protected diagnostics/logs;
- real SMTP flows where required;
- backup + independent second copy + isolated restore;
- exact operated commit;
- browser/operator acceptance;
- integrated actual-provider dry run.

No Hetzner, public DNS, public TLS or VPS evidence is required.
