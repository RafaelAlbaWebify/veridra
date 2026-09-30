# VERIDRA

VERIDRA is Webify's operator-local digital-presence assessment and client-delivery application.

It helps one Webify operator discover and qualify prospects, collect bounded public website evidence, prepare proposals, gate customer work behind accepted terms/payment evidence, manage remediation/reporting/monitoring, and prove changes through recurring Presence Care.

## Current product boundary

The supported product is:

- Windows operator-local;
- loopback-only;
- single Webify operator workspace;
- not a hosted SaaS;
- not a customer portal;
- not dependent on public DNS/TLS/VPS hosting;
- not dependent on SaaS plans, seats or workspace quotas.

The repository still contains historical SaaS/standalone modules for compatibility and tests. They are deliberately excluded from VERIDRA_ENV=operator.

## Core workflow

discover → qualify → audit → outreach eligibility → conversation → proposal → customer/work-start gate → project → delivery → acceptance → Presence Care/proof

Commercial lead score never overrides outreach/privacy eligibility.

## Evidence boundary

VERIDRA performs bounded public checks covering technical SEO fundamentals, crawl/indexability signals, AI crawler policy and technical readiness, trust/business/contact signals, accessibility heuristics, passive public security/email-domain posture, structured data and page-level evidence.

It is not a penetration-testing tool, a Semrush/backlink/traffic/rank database, proof of universal AI visibility, an accounting system or a payment authority.

## Operator runtime

Supported Windows workflow:

    cd C:\Users\ralba\Documents\GitHub\veridra
    .\VERIDRA_OPERATOR_START.bat

or:

    powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\windows\veridra-local.ps1 operator-start
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\windows\veridra-local.ps1 operator-open

Default URL: http://127.0.0.1:8010/agency

In operator mode the sole active loopback owner is auto-resolved; browser login is not part of the normal workflow.

## Runtime operations

    powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\windows\veridra-local.ps1 operator-restart
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\windows\veridra-local.ps1 status
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\windows\veridra-local.ps1 operator-preflight
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\windows\veridra-local.ps1 backup
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\windows\veridra-local.ps1 recovery-test

## Provider boundaries

- Stripe Presence Care: external payment/subscription authority; VERIDRA records bounded provider references and lifecycle state.
- SMTP: optional report-delivery channel, not required for the baseline workflow.
- Customer communications/signatures: normally external; VERIDRA stores evidence/references.
- Accounting/tax: external statutory process; VERIDRA is not the ledger of record.

## Quality and readiness

Repository CI includes Ruff, mypy, pytest and acceptance checks.

Readiness requires:

1. no SaaS/legacy dead ends in the supported runtime;
2. server-side enforcement of commercial/privacy state transitions;
3. green CI;
4. a fresh Windows operator acceptance run;
5. useful real-prospect discovery evidence before any real outreach.

See docs/product/agency-operator-workflow-audit.md, docs/runtime-route-policy.md, docs/product/strategy-and-roadmap.md and docs/operations/webify-b2b-outreach-compliance.md.

## Safety boundary

VERIDRA collects bounded public evidence. It rejects unsafe/private targets and does not perform active exploitation, credential attacks, brute-force discovery, mail-server probing or penetration testing.

Accessibility findings are heuristics, not conformance certification. AI readiness/crawler findings do not prove actual model visibility.
