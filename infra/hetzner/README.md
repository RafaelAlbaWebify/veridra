# Hetzner first-host provisioning

This optional Terraform layer provisions the preferred first VERIDRA VM. The application deployment itself remains provider-neutral in `deployment/`.

The configuration follows the current `hetznercloud/hcloud` provider and uses `location` rather than the deprecated `datacenter` field. The provider credential is intentionally not represented as a Terraform variable: supply `HCLOUD_TOKEN` through the operator environment or an appropriate secret mechanism.

## What it creates

- one Ubuntu 24.04 server;
- one operator SSH public key;
- one firewall attached at server creation;
- provider server backups enabled;
- delete/rebuild protection enabled;
- public IPv4 and IPv6;
- labels identifying production/single-writer topology.

Inbound firewall rules permit:
- TCP/22 only from explicitly supplied trusted CIDRs;
- TCP/80 from the Internet;
- TCP+UDP/443 from the Internet;
- ICMP for normal network operation/diagnostics.

Port 8000 is not exposed by the provider firewall and must also remain unpublished by Docker Compose.

## Before provisioning

1. Create a dedicated Hetzner Cloud project for VERIDRA.
2. Create an API token with the minimum permissions required for provisioning and keep it outside Git/chat/docs.
3. Generate/use a dedicated operator SSH key pair; Terraform receives only the public key.
4. Determine the current trusted public administration CIDR(s). Do not open SSH to `0.0.0.0/0` or `::/0` as a convenience default.
5. Re-check the chosen server type/location availability and price immediately before apply.

## Recommended Windows / PowerShell workflow

From the repository root:

```powershell
cd .\infra\hetzner
```

If the default public key does not exist yet:

```powershell
ssh-keygen -t ed25519
```

Create the ignored `terraform.tfvars` safely. Replace the example CIDR with the operator's real public IP/network; `/32` is appropriate for one IPv4 address:

```powershell
.\prepare.ps1 -SshCidr '203.0.113.42/32'
```

The helper rejects open-to-world SSH CIDRs and writes only public/non-secret infrastructure values. Review `terraform.tfvars` before continuing.

Set the Hetzner token only in the current PowerShell process. Do not paste the real value into Git, documentation, tickets or chat:

```powershell
$env:HCLOUD_TOKEN = '<local secret value>'
```

Run the guarded wrapper without `-Apply` first:

```powershell
.\provision.ps1
terraform show .\veridra.tfplan
```

The first command performs init, format check, validation and plan only. No infrastructure is changed.

After reviewing and accepting the plan:

```powershell
.\provision.ps1 -Apply
```

The wrapper applies the exact saved plan and removes the plan file after a successful apply.

## Direct Terraform workflow

For a non-Windows operator or advanced troubleshooting:

```bash
cd infra/hetzner
cp terraform.tfvars.example terraform.tfvars
# Edit only non-secret infrastructure values/public key.
export HCLOUD_TOKEN='...'
terraform init -input=false
terraform fmt -check -recursive
terraform validate -no-color
terraform plan -input=false -out=veridra.tfplan
terraform show veridra.tfplan
terraform apply -input=false veridra.tfplan
```

`terraform.tfvars`, Terraform state, `.terraform/` and `*.tfplan` are gitignored by this bundle.

Record the returned server ID and IP addresses as deployment evidence. Then create the application's DNS A/AAAA records at the actual DNS provider and follow `docs/operations/first-host-acceptance.md` and `docs/operations/single-host-deployment.md`.

## Boundaries

Terraform intentionally does not:
- create DNS records because the production DNS provider is not yet fixed;
- store application/SMTP/Stripe secrets;
- install or launch VERIDRA;
- prove provider backups are sufficient;
- create off-host application backups;
- grant any outreach/production-readiness credit merely because `terraform apply` succeeds.

A real M2 readiness increase requires the application to be deployed and externally validated on this or an equivalent host.

REAL OUTREACH COUNT remains 0.
