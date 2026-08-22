# Initial production provider recommendation — 22 August 2026

This document records the recommended first production environment for Veridra. It is a decision aid, not evidence that any external account, subscription, DNS record or paid resource has been created.

## Hosting recommendation

Recommended default: **Hetzner Cloud CX33 in Nuremberg, Germany**.

Current fit:

- x86 Intel/AMD architecture;
- 4 vCPU;
- 8 GB RAM;
- 80 GB local SSD/NVMe-class server storage;
- EU location with the application, identity SQLite database and Docker named tenant-data volume on one host;
- sufficient initial memory headroom for the Python web process plus bounded Playwright/Chromium audit work without starting on a 4 GB production host;
- compatible with the repository's provider-neutral Docker Compose/Caddy deployment bundle;
- free Hetzner Cloud Firewall capability;
- Hetzner provides an account-level Data Processing Agreement workflow for processor obligations under GDPR.

Pricing observed from Hetzner's official post-15-June-2026 price-adjustment documentation:

- CX33: **€8.49/month excluding VAT and excluding Primary IPv4**;
- Primary IPv4: **€0.50/month excluding VAT**;
- automated Hetzner server backups: **20% of the server price**, providing seven backup slots.

Provider snapshots/backups are an additional recovery layer, not a replacement for `veridra-backup`. The Compose bundle keeps `veridra_data` as a Docker named volume on the server disk, so whole-server backups include that local Docker state; do not move Veridra durable state to an attached provider Volume without separately confirming its backup treatment.

### Initial network policy

Use one public IPv4 plus IPv6 if desired. Apply a Hetzner Cloud Firewall before exposing the server:

- allow TCP 80 from the Internet for Caddy ACME/HTTP redirect;
- allow TCP 443 from the Internet;
- allow UDP 443 from the Internet for HTTP/3;
- allow TCP 22 only from known operator source addresses where practical; otherwise require SSH keys and harden SSH before customer traffic;
- do not expose TCP 8000 publicly;
- allow normal outbound traffic so DNS, HTTPS audit targets, Stripe and authenticated SMTP can operate.

The Compose bundle publishes only Caddy on 80/443. Veridra remains private on the Docker network.

## Transactional email recommendation

Recommended default for initial testing/launch: **Resend SMTP** using authenticated STARTTLS on port 587.

Current official free-tier limits are 3,000 transactional emails/month and 100/day. Resend supports SMTP on port 587 with username `resend`, an API key as the password, and a verified sending domain.

This aligns with both Veridra and the recommended host:

- Veridra already supports verified TLS SMTP/STARTTLS;
- Hetzner permits outbound port 587 without waiting for ports 25/465 to be unblocked;
- the initial volume is ample for signup verification, password reset and invitation traffic before real customer scale.

Brevo remains a valid alternative and currently allows 300 emails/day on its free plan, but its free plan applies Brevo branding. It is therefore the fallback when the higher daily allowance matters more than a minimal transactional-email surface.

Do not place a Resend API key in Git, Compose YAML or the example environment file. Store it only in the host-local `deployment/veridra.env` with restrictive permissions or a later runtime secret manager.

## Domain decision

**Not decided.**

Do not invent a production hostname in code or documentation. Before provisioning, choose either:

- a dedicated Veridra domain; or
- a controlled subdomain of an existing Webify-owned domain.

After selection, the same hostname must be used consistently for:

- `VERIDRA_DOMAIN`;
- `VERIDRA_TRUSTED_ORIGIN=https://<hostname>`;
- `VERIDRA_ALLOWED_HOSTS=<hostname>`;
- Caddy DNS/TLS;
- Resend sending-domain/DNS records where applicable;
- Stripe Checkout/Portal/webhook public URLs when paid billing is enabled.

## Launch size and scaling trigger

Start with CX33 rather than a smaller 4 GB server because audits invoke Chromium and Veridra currently combines web, local SQLite/filesystem state and bounded monitoring work on one host.

Do not add a second web replica as the first scaling action. The current persistence contract remains single-writer. Scale vertically first if any of these are observed under real load:

- repeated memory pressure or OOM kills;
- audit latency caused by sustained CPU contention;
- worker runs regularly exceeding their scheduling interval;
- durable disk usage approaching a conservative operating threshold.

A move to multi-host/shared persistence requires an explicit architecture redesign rather than an infrastructure toggle.

## Required steps before any purchase becomes a launch

1. Choose the production domain/hostname.
2. Create the hosting account/project and conclude the appropriate DPA.
3. Provision the selected EU x86 server with Primary IPv4 and firewall rules.
4. Install Docker Engine + Compose plugin and deploy the repository's `deployment/` bundle.
5. Create and verify the transactional-email domain/provider and configure SMTP port 587 credentials.
6. Publish Terms and Privacy URLs.
7. Run `veridra-production-preflight` (with `--require-stripe` only when paid launch is intended).
8. Point public DNS at the host and allow Caddy to obtain TLS.
9. Run `veridra-deployment-check` from outside the host.
10. Complete a real email-verified signup journey.
11. If paid launch is enabled, configure Stripe Products/Prices, Billing Portal and webhook, then prove Checkout → webhook reconciliation → entitlement.
12. Configure off-host verified backups and the bounded monitoring-worker schedule before relying on the service operationally.

## Sources checked for this recommendation

The recommendation was based on current official provider documentation checked on 22 August 2026: Hetzner cloud/server pricing and specifications, Primary IPv4 pricing, Cloud Firewall pricing, cloud backup pricing, DPA documentation and SMTP port restrictions; plus Resend SMTP and free-tier quota documentation. Re-check provider pricing and plan availability immediately before creating a paid resource because external prices can change independently of this repository.
