# Webify WordPress Care: local lab operations (experimental)

This command is **not** a commercial managed WordPress service and does not connect to external client sites. It only operates the known Docker Desktop local laboratory `webify-wp-lab` (WordPress at 127.0.0.1:8088).

Prerequisites: Docker context `desktop-linux`, the existing lab `compose.yaml`, and the running `webify-wp-lab` services. It does not interact with VERIDRA's customer databases, the 8089 restore environment, or any remote site.

## One-step Windows run

From the VERIDRA repository:

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\tools\wordpress_care_lab.ps1 -Action inspect
pwsh -NoProfile -ExecutionPolicy Bypass -File .\tools\wordpress_care_lab.ps1 -Action backup
```

- `inspect`: confirms Docker context, lab containers, HTTP 200, WordPress version, a SQL read and cached update counts. It does **not** initiate update queries or mutate WordPress.
- `backup`: performs the above plus a stopped (cold) snapshot of *only* `webify-wp-lab_db_data` and `webify-wp-lab_wp_data`, verifies tar readability, stores SHA-256, restarts laboratory services even on a caught backup failure.
- Results: `%USERPROFILE%\Documents\WebifyLabs\wordpress-care\acceptance\care-maintenance\care-*.json`; backup archives stay under the existing lab `backups` folder and may contain secrets. **Never commit artifacts/backups to GitHub.**

### Limitations and next release gates

A readable tar archive alone is not proof of recoverability; the previous human-run isolated 8089 restore demonstrated that separately. New backups must also be periodically restored in a disposable isolated environment. The script is deliberately lab-only and cannot update plugins, provision client access, or promise 24x7 coverage. For production managed care we still need: secret storage, authorized per-customer connectors, non-disruptive database-aware backups, off-site retention, scheduled execution, health probes beyond HTTP status, staging, safe updates, rollback, incident SLA and an actual cost model. No automatic updates or real outreach are authorized by this change.
