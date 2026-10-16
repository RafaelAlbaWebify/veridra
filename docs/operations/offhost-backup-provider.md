# Optional cloud-backup experiment — not a #296 requirement

Status: **OPTIONAL / RETAINED FOR FUTURE USE**

The Backblaze B2 + restic design in this repository was created for a cloud-hosted deployment model that is no longer the canonical first-customer architecture.

## Current backup requirement

VERIDRA runs on Rafael's Windows PC. #296 requires:
- one verified consistent VERIDRA backup;
- one independent operator-controlled second copy outside the live application data tree;
- one isolated restore test.

The second copy may be an external drive or another deliberately selected medium. A paid cloud backup account is **not mandatory**.

## Retained B2 design

The existing B2/restic scripts and documentation may be reused later if Webify explicitly decides that cloud backup is useful. They must not:
- trigger account/payment setup merely to pass readiness;
- be treated as a blocker;
- increase operability without real evidence;
- override the local-PC architecture.

If B2 is adopted later, the prior EU-region, least-privilege, client-side encryption and restore-testing controls should be revalidated against then-current provider terms.

## Verified independent second copy (Windows operator)

The operator can use `tools/independent_backup_copy.py` with a verified, quiesced VERIDRA backup ZIP and an existing directory on an external drive or separate network share:

```powershell
& .\.venv\Scripts\python.exe tools\independent_backup_copy.py --source "C:\\path\\to\\VERIDRA-backup.zip" --destination-dir "E:\\VERIDRA-Independent"
```

The command refuses same-volume copies and existing destination files, copies through a temporary file and verifies the SHA-256 digest before and after publishing. It records status, size, SHA-256 and destination volume **without copying customer data into the evidence text**. This does not prove physical device independence (e.g. partitions on one disk) or recoverability: identify a genuinely separate device/share and run the existing isolated recovery test using the second copy before release. Do not upload the backup ZIP, customer records or credentials into chat.
