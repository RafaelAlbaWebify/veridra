# First production VM architecture

Status: M2 deployment baseline. This document selects the first deployment shape; it does not prove that a production environment exists.

## Decision

Deploy the first VERIDRA production instance on one EU Linux VM. Hetzner Cloud is the preferred first provider because it offers inexpensive EU virtual machines, firewalls, backups/snapshots and volumes while preserving the current single-writer persistence model. The deployment pack remains provider-neutral and can run on another conventional Linux VM.

Preferred initial sizing: 4 vCPU / 8 GB RAM / about 80 GB local NVMe or better. Start in an EU datacenter. Do not add a second application replica until shared persistence/concurrency has been deliberately redesigned and tested.

## Why a VM

VERIDRA currently combines SQLite with filesystem tenant state. The web process and bounded monitoring worker must operate on the same durable state tree. A single VM lets both processes share `/var/lib/veridra` without pretending independent local volumes form a cluster.

This choice deliberately rejects Kubernetes, multi-replica PaaS defaults and separately persisted web/worker services for the first-customer phase.

## Runtime layout

- Caddy terminates public HTTPS on ports 80/443.
- `veridra-api` runs in a private Docker network on port 8000 and is never published directly.
- the bounded monitoring worker uses the same image and same `/var/lib/veridra` persistent mount;
- host systemd timer invokes the worker through `flock` so runs do not overlap;
- runtime secrets live in a root-readable environment file outside the repository;
- app state is stored on the VM durable filesystem under `/srv/veridra/data`, bind-mounted to `/var/lib/veridra`;
- Caddy certificate/config state is stored separately under `/srv/veridra/caddy`.

## Network boundary

Inbound provider firewall:
- TCP 22 only from the operator's trusted administration source where practical;
- TCP 80 from Internet for ACME/HTTP redirect;
- TCP 443 from Internet;
- deny everything else.

Docker publishes only Caddy's 80/443 ports. The application port remains internal to the Compose network.

## Persistence

One canonical state root:

`/srv/veridra/data` -> `/var/lib/veridra`

It contains the identity SQLite DB, identity-email evidence, tenant data and durable monitoring state. Do not place these in the container writable layer.

## Backup strategy

Provider VM backups are useful disaster-recovery layers but are not sufficient by themselves. Application-consistent backups must capture the whole VERIDRA state set together and must be restore-tested.

Before first external testing:
1. configure provider backups/snapshots;
2. create an application-consistent backup procedure for `/srv/veridra/data`;
3. copy protected backups off the VM;
4. restore one backup into an isolated instance;
5. require `/health/ready` and synthetic commercial checks after restore.

If a separate provider volume is used for VERIDRA data, verify whether provider server backups include that volume. Never assume they do.

## Supervision

- Docker restart policy supervises the web and proxy containers.
- systemd timer invokes `deploy/vm/worker-run.sh`.
- the worker script uses a host lock and runs one bounded worker container.
- external monitoring must probe `/health/live` and `/health/ready` independently.

## Go-live gates

This architecture decision is IMPLEMENTED as deployment tooling only. M2 remains incomplete until the actual environment proves:
- public DNS and TLS;
- provider firewall;
- durable state survives container replacement;
- web and worker supervision;
- live/readiness monitoring;
- real SMTP delivery on the public origin;
- scheduled backups plus successful isolated restore;
- production preflight and deployment check;
- exact deployed commit recorded.

REAL OUTREACH COUNT remains 0 until #284/#296 explicitly pass.
