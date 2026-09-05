# First production VM provider decision

Status: M2 architecture decision. The canonical deployment implementation is `deployment/` and `docs/operations/single-host-deployment.md`. This document selects the preferred first provider/profile only; it does not prove that a hosted environment exists.

## Decision

Use one EU Linux VM for the first VERIDRA deployment. Hetzner Cloud is the preferred first provider because its EU VM offering is inexpensive and compatible with VERIDRA's current single-writer SQLite + filesystem persistence model. The canonical `deployment/` bundle remains provider-neutral and can run on another conventional Linux VM if provider constraints change.

Initial target sizing: about 4 vCPU, 8 GB RAM and 80 GB durable SSD/NVMe or better. Do not add a second application replica until shared persistence/concurrency has been deliberately redesigned and tested.

## Why one VM

VERIDRA's web process and bounded monitoring worker need access to the same durable `/var/lib/veridra` state. A single host preserves this boundary without pretending separate local volumes form a cluster. This deliberately avoids Kubernetes, horizontally scaled PaaS defaults and independent web/worker storage for the first-customer phase.

## Canonical implementation

Use only:

- `deployment/compose.yaml`
- `deployment/Caddyfile`
- `deployment/veridra.env.example`
- `deployment/worker-run.sh`
- `deployment/backup-run.sh`
- `deployment/systemd/*`
- `docs/operations/single-host-deployment.md`
- `docs/operations/backup-restore.md`

The temporary `deploy/vm/` experiment has been removed so there is one deployment path.

## Network and persistence boundary

- Caddy is the only Internet-facing service and terminates TLS.
- VERIDRA port 8000 remains private to the Compose network.
- web and worker share one durable `veridra_data` volume.
- secrets remain in the host-local `deployment/veridra.env` or an external secret manager; the populated file is never committed.
- provider firewall exposes only administration access plus public HTTP/HTTPS required for TLS/application traffic.

## Backup boundary

Provider snapshots/backups are only an additional disaster-recovery layer. VERIDRA's application backup requires all writers to be quiesced and uses the existing `veridra-backup` command. Verified archives must also be copied to independent off-host storage and periodically restored in isolation.

If a provider volume is attached, explicitly verify whether server-level backups include that volume. Never assume they do.

## Operability rule

Selecting a provider and implementing deployment automation receives no DEPLOYED or EXTERNALLY VERIFIED credit. M2 improves operability only after the real host proves DNS/TLS, firewall, durable persistence, supervision, backups/restore and public-origin checks.

REAL OUTREACH COUNT remains 0 until #284/#296 explicitly pass.
