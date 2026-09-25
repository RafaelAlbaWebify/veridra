# Historical cloud-host option — not canonical

Status: **DEPRECATED FOR FIRST-CUSTOMER READINESS**

This document previously selected Hetzner Cloud for a hypothetical public Linux deployment.

That is **not** VERIDRA's intended first-customer operating model.

## Current canonical decision

VERIDRA is operated locally on Rafael's Windows PC:
- loopback-only;
- no public application exposure;
- no VPS/cloud application host;
- no public DNS/TLS requirement;
- customer interaction is operator-mediated.

See:
- `docs/WINDOWS_LOCAL_OPERATIONS.md`
- issue #296

## Why this file remains

The Linux/Hetzner work is retained as optional future research in case VERIDRA later becomes a directly hosted/customer-accessible SaaS product.

It must not:
- be treated as a readiness blocker;
- trigger account/payment setup;
- be used to claim operability progress;
- override the Windows-local architecture without a new explicit architecture decision.

No Hetzner account, server or paid infrastructure is required for the current model.
