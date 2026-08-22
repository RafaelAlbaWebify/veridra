# Single-host production deployment

The `deployment/` bundle is a provider-neutral Docker Compose baseline for Veridra's current single-writer persistence model. It is intended for one Linux host with a public IPv4/IPv6 address, a DNS name and Docker Engine with the Compose plugin.

It runs:

- `web` — the Veridra API/browser runtime, available only on the private Compose network;
- `caddy` — the only Internet-facing service, publishing TCP 80/443 and UDP 443 and obtaining/renewing public TLS certificates automatically once DNS points at the host;
- `worker` — the same Veridra image with the bounded monitoring-worker command, available as an on-demand Compose profile for a host scheduler;
- one named `veridra_data` volume shared by web and worker, plus Caddy's certificate/config volumes.

This is deliberately one application writer topology. Do not scale `web` horizontally or start overlapping worker invocations without redesigning shared persistence/locking first.

## 1. Prepare the host

Clone the repository onto the host and work from the `deployment/` directory. Copy the example environment file:

```text
cp veridra.env.example veridra.env
chmod 600 veridra.env
```

Edit `veridra.env` with the real domain, trusted origin, allowed host, Terms/Privacy URLs and SMTP settings. If paid launch is required, also configure the real Stripe keys, webhook secret and Price IDs. The real `deployment/veridra.env` is gitignored and must remain host-local or be generated from a secret manager.

The values of `VERIDRA_DOMAIN`, `VERIDRA_TRUSTED_ORIGIN` and `VERIDRA_ALLOWED_HOSTS` must describe the same public hostname. Point DNS A/AAAA records for that hostname at the server and allow inbound TCP 80/443 plus UDP 443. Do not publish container port 8000 on the host firewall or Docker command line.

## 2. Validate configuration before launch

Build the image and validate the Caddy configuration:

```text
docker compose --env-file ./veridra.env -f compose.yaml build web worker
docker compose --env-file ./veridra.env -f compose.yaml run --rm caddy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
```

Run Veridra's read-only production preflight with the same environment and durable volume:

```text
docker compose --env-file ./veridra.env -f compose.yaml run --rm web veridra-production-preflight
```

For a paid launch:

```text
docker compose --env-file ./veridra.env -f compose.yaml run --rm web veridra-production-preflight --require-stripe
```

Do not start production if preflight returns exit code `2`.

## 3. Start web and TLS proxy

```text
docker compose --env-file ./veridra.env -f compose.yaml up -d web caddy
```

Only Caddy publishes host ports. Veridra itself is exposed only as `web:8000` on the private Compose network. Caddy checks `/health/ready` and preserves the public `Host` header while stripping `Forwarded` and `X-Forwarded-*` before proxying, matching Veridra's safest proxy boundary without trusting a dynamic container IP.

Caddy access logs are JSON to stdout. The supplied filter replaces the value of any `token` query parameter with `REDACTED` and removes direct/client IP fields plus `X-Forwarded-For` from the log event. Caddy also redacts credential-style headers by default. Keep this filter if proxy access logging is enabled; do not replace it with raw common-log output.

Check service state:

```text
docker compose --env-file ./veridra.env -f compose.yaml ps
docker compose --env-file ./veridra.env -f compose.yaml logs --tail=100 web caddy
```

## 4. Run the remote deployment gate

From a separate operator machine or CI runner that can reach the public hostname, run:

```text
veridra-deployment-check --origin https://app.example.com
```

Use the actual public origin. The checker validates public DNS addresses, pins each connection to the validated address while preserving TLS SNI/Host, and checks the canonical health endpoints, signup surface, hidden production-only routes, security headers and cache controls. A multi-address DNS record is tried safely across its already validated public addresses.

A successful remote deployment check is required before treating the host as ready for customer traffic.

## 5. Schedule the bounded monitoring worker

The `worker` service is intentionally not a daemon. Invoke it from the host scheduler and allow each run to exit before the next run begins. Example cron entry every five minutes when the repository lives at `/opt/veridra` uses `flock` so a slow previous run cannot overlap the next invocation:

```text
*/5 * * * * flock -n /var/lock/veridra-worker.lock sh -c 'cd /opt/veridra/deployment && /usr/bin/docker compose --env-file ./veridra.env -f compose.yaml run --rm worker >> /var/log/veridra-worker.log 2>&1'
```

Adjust cadence based on the monitoring product schedule. If `flock` is unavailable, use a systemd timer or another scheduler with an explicit no-overlap guarantee rather than plain recurring cron.

## 6. Backup

Veridra backup requires explicit writer quiescence. Stop web traffic and ensure no monitoring-worker or billing writer is active before asserting `--confirm-quiesced`.

Example with a host backup directory mounted outside `/var/lib/veridra`. A UTC timestamp is part of every archive name because verified backup intentionally refuses to overwrite an existing archive:

```text
mkdir -p /opt/veridra-backups
BACKUP_NAME="veridra-$(date -u +%Y%m%dT%H%M%SZ).zip"
docker compose --env-file ./veridra.env -f compose.yaml stop web
docker compose --env-file ./veridra.env -f compose.yaml run --rm -v /opt/veridra-backups:/backups worker veridra-backup backup --output "/backups/${BACKUP_NAME}" --confirm-quiesced
docker compose --env-file ./veridra.env -f compose.yaml start web
```

Copy verified backups off the server. A single VPS plus a local Docker volume is not itself a disaster-recovery strategy.

## 7. Upgrade

Pull the intended repository revision, rebuild, run preflight, then replace the web container:

```text
docker compose --env-file ./veridra.env -f compose.yaml build web worker
docker compose --env-file ./veridra.env -f compose.yaml run --rm web veridra-production-preflight
docker compose --env-file ./veridra.env -f compose.yaml up -d web caddy
```

After every deployment, run `veridra-deployment-check` from outside the host and then exercise the controlled signup/billing/agency acceptance path appropriate to the release.

## Provider boundary

This bundle does not select or provision a VPS vendor, DNS registrar/provider, SMTP service or Stripe account. It assumes a Linux host already exists. Provider selection should therefore be based on current cost, durable storage/backup options, outbound SMTP policy, support and the operator's desired management burden rather than changing Veridra's application architecture.
