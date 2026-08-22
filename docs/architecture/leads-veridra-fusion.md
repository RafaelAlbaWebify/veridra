# LEADS + Veridra fusion

## Product decision

Veridra is the canonical Webify acquisition workbench.

The former `leadmap-local` / LEADS application remains a source repository during migration, but it is no longer the intended operational boundary. The end-state workflow is one application:

> discover business -> qualify commercial fit -> audit website -> classify refurbishment opportunity -> approve outreach -> track conversation/proposal -> convert to client project -> prove improvement

The primary success metric is Webify customer acquisition and refurbishment revenue, not Veridra subscription MRR.

## Why the applications are being fused

LEADS already modeled the commercial path as `qualified -> shortlisted -> sent_to_veridra -> veridra_reviewed -> approved_for_outreach`. Those handoff states existed only because discovery and website assessment lived in separate applications.

The fused model removes that transport boundary. A Veridra `Prospect` persists discovery evidence and Stage-A business qualification before any deep website audit. The same record then advances through audit, outreach and customer states.

Inbound website-audit form submissions remain `AuditLead` records. They carry consent and delivery semantics and must not be conflated with outbound Webify prospect research.

## Canonical prospect lifecycle

The initial lifecycle is:

- `new`
- `needs_review`
- `qualified`
- `shortlisted`
- `ready_for_audit`
- `audited`
- `approved_for_outreach`
- `contacted`
- `responded`
- `conversation`
- `proposal`
- `customer`
- terminal/support states: `unsuitable`, `duplicate`, `archived`

There is deliberately no `sent_to_veridra` or `veridra_reviewed` state because Veridra now owns both sides of the former handoff.

## Stage A: commercial qualification

The LEADS Webify Qualification v0.1 gate is retained as a seven-criterion, 0-2 scoring model:

1. active real business;
2. website commercial importance;
3. business economic value;
4. business size/fit;
5. decision-maker reachability;
6. website/platform manageability;
7. absence of an obvious existing agency/internal web team.

Maximum score: 14.

- 11-14: `send_to_audit`;
- 8-10: `hold`;
- 0-7: `reject`.

An explicit rejection reason overrides the numeric score. Human-readable reasoning is mandatory so the score never becomes opaque automation.

## Rejection evidence

The retained rejection taxonomy is:

- `BUSINESS_INACTIVE`
- `TOO_SMALL_LOW_VALUE`
- `TOO_LARGE`
- `WEBSITE_NOT_IMPORTANT`
- `INTERNAL_WEB_TEAM`
- `AGENCY_PRESENT`
- `NO_CONTACT_ROUTE`
- `TECH_TOO_COMPLEX`
- `NO_MEANINGFUL_FINDINGS`
- `FINDINGS_NOT_FIXABLE`
- `FIX_TOO_LARGE_FOR_OFFER`
- `LOW_COMMERCIAL_IMPACT`
- `EVIDENCE_UNCERTAIN`
- `DUPLICATE`
- `OTHER`

These reasons are commercial-learning data. They should later be aggregated to show whether discovery sources, ICP assumptions, audit criteria or the Webify offer are wrong.

## Migration sequence

1. **Prospect foundation** — canonical prospect model, tenant persistence and API in Veridra.
2. **LEADS import adapter** — deterministic import of existing `leadmap-local` shortlist/handoff data without re-discovery.
3. **Discovery engine** — migrate provider-neutral territory/query/normalization/deduplication logic into Veridra.
4. **Local discovery UI** — move the useful territory/business review experience into Veridra; do not copy framework complexity merely for parity.
5. **Audit conversion** — one action turns a qualified prospect website into the existing Veridra assessment/project pipeline and records the relationship.
6. **Opportunity qualification** — classify audit findings by Webify commercial usefulness (A/B/C/D), fixability and estimated effort.
7. **Outreach/pipeline** — manual outreach status, notes, proposal and customer outcome inside the same prospect record/workflow.
8. **Archive LEADS** — only after the migrated workflow can reproduce the operational discovery-to-audit path and required data from `leadmap-local`.

## Operating boundary

Discovery remains bounded and reviewable. Deep website assessment happens after commercial qualification, and outreach remains a human-reviewed business action. Technical findings must not be turned into sales urgency unless they are reproducible, commercially meaningful and realistically fixable by Webify.
