# VERIDRA first-production VM deployment pack

This directory turns `docs/operations/production-deployment.md` into an executable single-VM layout. It does not provision a cloud account or constitute deployment evidence by itself.

## Host prerequisites

- current Ubuntu or Debian LTS-class VM;
- Docker Engine with Compose plugin;
- public IPv4/IPv6 as required;
- DNS A/AAAA record for the application hostname;
- provider firewall allowing only administration plus HTTP/HTTPS;
- `/srv/veridra/data` and `/srv/veridra/caddy/{data,config}` created on durable host storage;
- `/etc/veridra/veridra.env` and `/etc/veridra/compose.env` owned by root and mode 600.

## Repository placement

Deploy the exact approved commit at `/opt/veridra`.

## Prepare directories

```bash
sudo install -d -m 0750 /srv/veridra/data
sudo install -d -m 0750 /srv/veridra/caddy/data /srv/veridra/caddy/config
sudo install -d -m 0700 /etc/veridra
```

Copy the example environment files outside the repository and populate them. Never place real secrets in Git.

## Build and start

```bash
cd /opt/veridra
docker compose --env-file /etc/veridra/compose.env -f deploy/vm/docker-compose.yml build web
docker compose --env-file /etc/veridra/compose.env -f deploy/vm/docker-compose.yml up -d caddy web
```

Check local container state, then public endpoints:

```bash
docker compose --env-file /etc/veridra/compose.env -f deploy/vm/docker-compose.yml ps
curl -fsS https://app.example.com/health/live
curl -fsS https://app.example.com/health/ready
```

## Install worker timer

```bash
sudo cp deploy/vm/systemd/veridra-worker.service /etc/systemd/system/
sudo cp deploy/vm/systemd/veridra-worker.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now veridra-worker.timer
systemctl list-timers veridra-worker.timer
```

The worker uses `flock` and exits cleanly if a prior invocation is still active.

## Update procedure

1. record current commit and take an application-consistent backup;
2. pull/checkout the exact approved commit;
3. rebuild the image;
4. stop the worker timer while migrations/recovery are occurring;
5. restart one web container;
6. require `/health/live` and `/health/ready` success;
7. exercise login and controlled password reset;
8. re-enable worker timer;
9. run production preflight/deployment acceptance and record evidence.

## Rollback

Application rollback and data rollback are separate operations. Do not restore only one side of a consistency set. Follow `docs/operations/production-deployment.md` and restore identity DB, identity-email evidence, tenant state, billing/subscription evidence and monitoring state together.

## Security rules

- never publish port 8000;
- never add multiple web replicas on local copied state;
- never commit `/etc/veridra/*.env`;
- never trust arbitrary forwarded headers;
- never consider provider backups verified until an isolated restore succeeds;
- REAL OUTREACH COUNT remains 0 until #284/#296 pass.
