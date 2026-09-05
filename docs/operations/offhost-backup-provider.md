# Off-host backup provider decision

Status: **PRODUCTION-INTENDED / NOT VERIFIED**

Decision date: 2026-09-05

## Decision

Backblaze B2 Cloud Storage in **EU Central (Amsterdam)** is the production-intended off-host disaster-recovery destination for the first VERIDRA deployment.

VERIDRA's own quiesced `veridra-backup` ZIP remains the application-consistent source artifact. After the local backup service has completed and the web/worker are available again, a separate host service copies the newest verified ZIP into a **restic-encrypted repository** stored in B2 using B2's S3-compatible API.

This is deliberately separate from the Hetzner VM/provider account so a VM/disk/provider-account problem does not leave the only usable copy in the same compute failure domain.

## Selection basis

Current official material reviewed on 2026-09-05 states:

- Backblaze B2 accounts can be created in EU Central and that region stores account data in the Amsterdam data center;
- the selected account region determines where B2 data is stored, and Backblaze states data remains in that selected region unless the customer explicitly directs movement;
- the first 10 GB of B2 storage is currently free, making it suitable for the small first-customer backup set;
- Backblaze provides a GDPR-oriented DPA for EEA/EU residents;
- B2 exposes an S3-compatible API;
- B2 supports server-side AES-256 encryption, but the VERIDRA design does not rely on provider-side encryption alone.

Current restic documentation recommends using Backblaze B2 through its S3-compatible API rather than the direct B2 backend. Restic encrypts and authenticates repository content before it is stored remotely.

Alternatives considered:

- **Hetzner Object Storage**: operationally simple and EU-capable, but keeps compute and the off-host copy under the same provider/account; useful as a future additional copy, not preferred as the only off-host DR copy.
- **Wasabi**: EU-capable, but current Pay-as-You-Go terms impose a 1 TB monthly minimum and a 90-day minimum storage-duration charge, which is disproportionate for the first-customer backup volume.

Provider pricing/terms must be rechecked immediately before account creation.

## Data / privacy boundary

The uploaded object is a restic-encrypted copy of the already verified application backup archive. That archive may contain:

- VERIDRA user/account state;
- customer business contact/project/lifecycle records;
- assessment/report/monitoring evidence;
- billing/provider references;
- other durable VERIDRA state included by `veridra-backup`.

Rules:

- choose **EU Central** when the B2 account is created; region choice is an account-level decision and should be captured as evidence;
- use a dedicated bucket whose name contains no customer name, email, PHI or other personal data;
- use a dedicated least-privilege B2 application key scoped to the backup bucket where supported;
- do not use the master application key for routine backup automation;
- store B2 S3 credentials only in the root-owned production secret/config boundary;
- keep the restic repository password independent of the B2 credential and outside Git/chat/docs;
- protect the restic password separately from the B2 account so loss of the VM does not make recovery impossible;
- do not put personal/customer data in object names/tags/metadata;
- provider-side SSE may be enabled as defense in depth, but client-side restic encryption remains mandatory for this design.

## Host flow

1. `veridra-backup.service` quiesces application writers and creates a verified local ZIP under `/opt/veridra-backups`.
2. Its EXIT trap restarts the web runtime and the worker timer.
3. Only after local backup success, systemd triggers `veridra-offhost-backup.service`.
4. The off-host service reads `/etc/veridra/offhost-backup.env`, selects the newest local `veridra-*.zip`, and sends that archive to the configured restic repository.
5. The off-host service validates that the restic repository is readable and records a bounded snapshot result without logging credentials or backup contents.
6. Periodic isolated restore evidence must prove that a remote snapshot can be restored and then passed into the normal `veridra-backup restore` procedure.

The Internet upload is deliberately outside the quiesced application-backup critical section so customer-facing runtime is not held offline while remote replication occurs.

## Secret/config boundary

Tracked example: `deployment/offhost-backup.env.example`.

Production file: `/etc/veridra/offhost-backup.env`, owned by root and mode `0600`.

Required variables:

- `RESTIC_REPOSITORY` — B2 S3-compatible repository URL, e.g. `s3:https://<actual-b2-s3-endpoint>/<bucket>/veridra`;
- `RESTIC_PASSWORD_FILE` — root-readable path to the independent restic repository password;
- `AWS_ACCESS_KEY_ID` — B2 S3-compatible application key ID;
- `AWS_SECRET_ACCESS_KEY` — B2 S3-compatible application key secret;
- `AWS_DEFAULT_REGION` — actual B2 S3 region identifier from the created EU Central account.

Never commit the production file or password file.

## Initial provider setup gate

Before enabling the off-host service:

1. create the exact WEBIFY LIMITED Backblaze account in EU Central;
2. review then-current Terms, DPA, subprocessors, security/MFA, retention/deletion and incident/support posture;
3. create a dedicated private bucket;
4. verify the bucket/account region is EU Central;
5. enable provider-side encryption if applicable to the actual bucket/configuration;
6. create a least-privilege application key for that bucket;
7. install a supported current restic build on the host;
8. create a high-entropy restic repository password and preserve an independent recovery copy;
9. create `/etc/veridra/offhost-backup.env` and the password file with root-only permissions;
10. initialize the restic repository once;
11. trigger one real local application backup and verify the off-host snapshot appears;
12. restore the remote snapshot into an isolated host/directory;
13. validate the contained VERIDRA ZIP using the normal verified restore procedure;
14. record dates, provider/bucket region, snapshot ID, archive hash/size, restore result and deployed commit without recording credentials.

## Retention

Do not invent a production retention schedule solely to make configuration complete. During the first-customer dry run, preserve enough generations to demonstrate recovery and measure backup growth. Before production approval, freeze a retention policy consistent with operational recovery needs, statutory/customer retention duties and provider economics, then test `restic forget/prune` behavior on non-production evidence.

## Readiness classification

- Provider/architecture choice: **IMPLEMENTED**.
- Host off-host service/scripts: repository implementation may be **TESTED IN CI** once corresponding tests pass.
- Real B2 account/bucket: **NOT VERIFIED**.
- Real encrypted remote snapshot: **NOT VERIFIED**.
- Remote-to-isolated restore: **NOT VERIFIED**.
- M2 off-host backup gate: **NOT COMPLETE**.

**REAL OUTREACH COUNT = 0.**
