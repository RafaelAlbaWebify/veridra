# Webify / VERIDRA — non-destructive TRON data acceptance

Status: **operator evidence required**. Green CI proves synthetic compatibility,
not the contents or recoverability of a particular workstation.

## One-command acceptance (recommended)

From the checked-out `refactor/webify-operator-only` branch, in PowerShell:

```powershell
& .\\scripts\\windows\\veridra-commercial-local.ps1 data-audit
```

This action quiesces the managed Webify services for a consistent backup,
restarts them afterward, restores the latest snapshot to an isolated directory,
and writes a counts-only report to
`%LOCALAPPDATA%\\VeridraCommercial\\audits\\WEBIFY_DATA_AUDIT_*.json`.
It is **not** zero-interruption: backup briefly stops managed services.
Only share the JSON report; do not upload the actual backup or customer data.

## Safety boundary

1. Keep the currently functioning installation and `main` untouched.
2. From the `refactor/webify-operator-only` checkout, run the supported
   `scripts/windows/veridra-commercial-local.ps1` with `-Action backup`
   after following its documented local-operation procedure.
3. Run the same launcher with `-Action recovery-test`; it creates an
   isolated restore under `%LOCALAPPDATA%\\VeridraCommercial\\recovery-test-*`.
   Do **not** substitute live `data\\identity\\veridra.sqlite3` for the
   isolated restored SQLite file.
4. Identify the restored pair of paths in the same recovery-test directory:
   `identity\\veridra.sqlite3` and `tenants`.
5. From the repository root in PowerShell, inspect the restored pair (substitute
   the actual recovery-test folder):
   ```powershell
   python tools/webify_data_inventory.py `
     --identity-db "$env:LOCALAPPDATA\\VeridraCommercial\\recovery-test-YYYYMMDD_HHMMSS\\identity\\veridra.sqlite3" `
     --tenant-root "$env:LOCALAPPDATA\\VeridraCommercial\\recovery-test-YYYYMMDD_HHMMSS\\tenants"
   ```
6. Require `identity.state == "readable"` and
   `identity.integrity == "ok"`. `unsafe_snapshot` means WAL, SHM, or
   journal sidecars were found: do not infer missing records or delete
   anything; make a new consistent backup.
7. Review counts for projects, assessments, legacy workspace configs, plan
   history, and historical SaaS Stripe bindings. A zero count is evidence
   about the snapshot only, **not authorization to delete compatibility code**.
8. Retain the backup, original directory and the resulting summary. Do not
   paste customer files, passwords, Stripe secrets or the SQLite database into
   issues or pull requests.

The inventory performs counts only. It neither migrates nor repairs data,
and it does not establish full application-level restore compatibility by
itself. Release/merge still requires an operator acceptance using the
restored application data, including prospect-to-customer, reports and
Presence Care / customer billing where configured.
