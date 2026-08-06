# Veridra Windows-local operations

This workflow is for local evaluation before any cloud deployment.

## First setup

From the repository root, run:

```bat
VERIDRA_SETUP.bat
VERIDRA_CREATE_SHORTCUT.bat
```

Setup creates `.venv`, installs Veridra with development dependencies, installs Playwright Chromium, and creates the local application directories.

## Daily use

- `VERIDRA_OPEN.bat` starts Veridra if required and opens `http://127.0.0.1:8000/`.
- `VERIDRA_START.bat` starts without opening the browser.
- `VERIDRA_STOP.bat`, `VERIDRA_RESTART.bat`, and `VERIDRA_STATUS.bat` control the local process.
- `VERIDRA_TEST.bat` runs Ruff, strict mypy, and pytest.
- `VERIDRA_DIAGNOSTICS.bat` writes a redacted operational summary.

## Local data

Application state is stored beneath:

```text
%LOCALAPPDATA%\Veridra\data
```

Runtime PID and logs are stored beneath `%LOCALAPPDATA%\Veridra\runtime`. Backups are stored beneath `%LOCALAPPDATA%\Veridra\backups`.

The scripts bind only to `127.0.0.1:8000`. They do not expose Veridra publicly.

## Backup and restore

Create a backup:

```bat
VERIDRA_BACKUP.bat
```

Preview a restore:

```bat
VERIDRA_RESTORE.bat -BackupPath "C:\path\VERIDRA_BACKUP_YYYYMMDD_HHMMSS.zip"
```

Apply after reviewing the displayed source and target:

```bat
VERIDRA_RESTORE.bat -BackupPath "C:\path\VERIDRA_BACKUP_YYYYMMDD_HHMMSS.zip" -Apply
```

A pre-restore safety backup is attempted before replacement.

## Desktop shortcut

`VERIDRA_CREATE_SHORTCUT.bat` creates or replaces `Veridra.lnk` on the current user's Desktop without administrator rights. The shortcut launches `VERIDRA_OPEN.bat` with the repository root as its working directory.

## Acceptance boundary

Repository CI can verify script structure and application tests. Actual shortcut creation, clean-clone setup, browser onboarding, persistence, backup/restore, monitoring-worker operation, and complete end-to-end acceptance must still be executed on the target Windows workstation before issue #139 can close.
