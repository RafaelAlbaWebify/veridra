# Canonical operator-host acceptance

VERIDRA's first production/operator host is Rafael's Windows PC.

The old public-Linux-host acceptance path is no longer the canonical #296 gate.

## Acceptance target

Prove the actual Windows workstation can operate VERIDRA safely and repeatably while keeping the application private to the operator.

Required evidence:
1. exact repository commit;
2. loopback-only bind (`127.0.0.1`);
3. hardened operator-local runtime profile distinct from ordinary development mode;
4. durable state under the Windows-local data root;
5. web process and monitoring worker start/status/restart behavior;
6. protected diagnostics/logging;
7. backup creation;
8. independent second backup copy outside the live application data tree;
9. isolated restore and post-restore validation;
10. actual SMTP/provider workflows required by the business model;
11. browser/operator acceptance on the local origin.

## Explicit non-requirements

The following are not required:
- VPS provisioning;
- Hetzner;
- public DNS;
- public TLS;
- Caddy;
- inbound 80/443;
- Internet-facing VERIDRA;
- provider firewall evidence;
- public `veridra-deployment-check`.

## Safety boundary

No router port forwarding or LAN exposure is part of acceptance. If a future product requires customer-direct access, create a new architecture/validation workstream instead of weakening this boundary.
