# First-production DNS and TLS boundary

Status: architecture decision only; not deployment evidence.

## Decision

For the first Webify-operated VERIDRA deployment, keep authoritative DNS as a simple control-plane dependency and terminate public TLS on the VERIDRA host with Caddy.

Do **not** add a reverse-proxy/CDN/edge data-processing layer merely for the first launch. If the production domain already has a competent authoritative DNS provider, retain it unless there is a concrete security, reliability or operational reason to migrate nameservers.

This means the intended request path is:

`client -> public DNS resolution -> Hetzner host firewall -> Caddy :443 -> private web:8000`

The authoritative DNS provider publishes records; it is not intended to proxy HTTP traffic in this baseline.

## First-host DNS procedure

1. Record the exact production hostname and existing authoritative DNS provider.
2. Verify account ownership, MFA/access recovery and change permissions.
3. Create only the records required for the deployment, initially the application `A` record and `AAAA` only if IPv6 is deliberately enabled and firewall-tested.
4. Use a short but reasonable TTL during the controlled first deployment; restore a normal TTL after the origin is stable.
5. Confirm public resolution from outside the server.
6. Allow inbound TCP 80/443 and UDP 443 at the provider firewall; keep application port 8000 private.
7. Let Caddy obtain/renew certificates for the exact hostname.
8. Run `veridra-deployment-check --origin https://ACTUAL_HOSTNAME` externally after TLS is issued.
9. Record DNS provider, records, timestamps and evidence in the first-host acceptance record.

## Provider/subprocessor boundary

The exact authoritative DNS provider remains an external fact to verify when the production hostname is chosen. Provider identity is therefore **NOT VERIFIED** today.

The architecture intentionally avoids adding an HTTP proxy/CDN by default. If a future edge provider proxies customer traffic, performs WAF/bot processing, retains request metadata or terminates TLS away from the VERIDRA host, reassess:

- controller/processor role and DPA;
- request/IP/log data categories;
- processing regions and international transfers;
- retention/deletion;
- TLS/origin-authentication model;
- abuse/WAF rules and false-positive operational risk;
- subprocessor register and customer disclosures.

## Promotion rule

DNS architecture may be treated as **DEFINED** when this document exists. DNS/TLS may be treated as **DEPLOYED / EXTERNALLY VERIFIED** only after the real hostname resolves to the intended host, Caddy serves a valid certificate, external deployment checks pass, and the exact provider/account evidence is recorded.

REAL OUTREACH COUNT remains 0 until #284/#296 are complete and Rafael explicitly approves.
