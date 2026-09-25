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
