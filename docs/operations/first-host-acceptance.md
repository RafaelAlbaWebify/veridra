# First-host provisioning and acceptance

This is the operator bridge between repository implementation and M2 DEPLOYED/EXTERNALLY VERIFIED evidence.

## 1. Provision the host

Preferred route: `infra/hetzner/` Terraform. It creates the Ubuntu 24.04 host, restricted provider firewall, operator SSH public key, provider backups and delete/rebuild protection. Keep `HCLOUD_TOKEN` outside Git and do not send the token through chat, tickets or documentation.

A manually created equivalent EU Linux VM is acceptable if it satisfies the same controls.

## 2. DNS boundary

After provisioning, create the real application A/AAAA records at the selected DNS provider. DNS is intentionally not provisioned by the Hetzner Terraform module because Webify's production DNS provider is not yet fixed.

Record:
- hostname;
- A/AAAA targets;
- provider name;
- change timestamp;
- evidence that the records resolve publicly to the intended host.

## 3. Host prerequisites

Install Docker Engine + Compose using a currently supported distribution/provider path. Clone the repository at `/opt/veridra` and check out the exact candidate release commit.

Create `deployment/veridra.env` from the tracked example and set mode 600. Do not populate fake SMTP/Stripe credentials merely to pass configuration checks.

## 4. Validate before start

From `/opt/veridra/deployment`:

```bash
docker compose --env-file ./veridra.env -f compose.yaml build web worker
docker compose --env-file ./veridra.env -f compose.yaml run --rm caddy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
docker compose --env-file ./veridra.env -f compose.yaml run --rm web veridra-production-preflight
```

Use `--require-stripe` only after real Stripe test resources exist.

## 5. Start the public runtime

```bash
docker compose --env-file ./veridra.env -f compose.yaml up -d web caddy
sudo ./install-host-units.sh
```

Caddy must be the only Internet-facing application service. Port 8000 must remain private.

## 6. Capture host evidence

After public TLS is issued and health checks succeed:

```bash
sudo ./capture-host-evidence.sh
```

The output records commit, host/runtime versions, Compose state, timer states and public health responses without dumping the environment file or secret values.

From an external operator machine, also run:

```text
veridra-deployment-check --origin https://ACTUAL_HOSTNAME
```

## 7. Backup/restore evidence

Trigger one controlled application backup:

```bash
sudo systemctl start veridra-backup.service
sudo journalctl -u veridra-backup.service --since today --no-pager
sudo ls -lh /opt/veridra-backups/
```

Copy the resulting archive to independently durable off-host storage. Then restore a copy into an isolated environment following `docs/operations/backup-restore.md` and verify readiness, controlled sign-in, representative tenant/commercial state and monitoring history.

## 8. M2 promotion rule

Do not mark M2 complete merely because Terraform, Compose or systemd configuration exists. M2 can receive DEPLOYED/EXTERNALLY VERIFIED credit only after the actual host evidence proves:
- firewall and public DNS/TLS;
- durable application state;
- supervised web/worker behavior;
- health/logging operation;
- real backup creation and independent copy;
- isolated restore success;
- exact deployed commit.

SMTP/Stripe/provider E2E remain separate M3/M4 gates.

REAL OUTREACH COUNT remains 0.
