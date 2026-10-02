# Hosted H1 commercial integrity acceptance

Status: **COMPLETE**
Closed: 2026-10-02

## Scope

H1 proves the hosted product's commercial integrity baseline in repository regression evidence.

This is not hosted launch acceptance. Provider, live-host, real TLS/SMTP/Stripe and human acceptance remain later gates.

## Closure baseline

- Integrated transition acceptance commit: `f65f4caa`
- GitHub Actions run: `36990700714`
- Result: **success**
- Verify job: Ruff, strict mypy, pytest, deterministic audit and browser discovery acceptance passed.
- Windows job: portability, sales-contract Playwright and full operator Playwright acceptance passed.

## Acceptance matrix

| H1 criterion | Evidence | Result |
| --- | --- | --- |
| Signup/login/workspace/plan path coherent | `tests/test_signup_web.py`, `tests/test_browser_auth_web.py`, `tests/test_workspace_web.py`, `tests/test_plans_web.py` | PASS |
| Audit/project quotas enforced | `tests/test_tenant_assessment_usage.py`, `tests/test_tenant_project_api.py`, `tests/test_lead_project_conversion_api.py` | PASS |
| White-label/report/PDF entitlements enforced | `tests/test_agency_report_profile_edit_web.py`, `tests/test_agency_report_web.py`, `tests/test_tenant_report_api.py` | PASS |
| Monitoring metered | `tests/test_tenant_monitoring_execution.py`, `tests/test_monitoring_service.py`, `tests/test_agency_monitoring_web.py` | PASS |
| Embedded lead forms tenant-bound and metered | `tests/test_agency_lead_form_web.py`, `tests/test_tenant_bound_lead_capture.py` | PASS |
| Lead source evidence tenant-scoped | `tests/test_tenant_bound_lead_capture.py`, `tests/test_lead_project_conversion_api.py` | PASS |
| Team seats enforced | `tests/test_tenant_seat_entitlements.py`, `tests/test_tenant_team_web.py` | PASS |
| Downgrade/recovery paths do not dead-end | report downgrade recovery, lead-form cleanup, team-member deactivation, monitoring-to-manual recovery, plus `tests/test_hosted_commercial_integrity_acceptance.py` | PASS |

## Integrated transition guardrail

`tests/test_hosted_commercial_integrity_acceptance.py` exercises one tenant through:

`Agency → Professional → Free → Suspended → Agency recovered`

It verifies:

- tenant project isolation;
- white-label and embedded-form feature transitions;
- project capacity enforcement;
- PDF quota enforcement;
- zero monitoring allowance on Free;
- suspended feature/project/seat shutdown without data deletion;
- recovery to active Agency capability;
- reservation cleanup after recovery.

## Runtime separation regression

A hosted entitlement regression previously broke operator autonomous monitoring because the scheduler applied hosted plan limits in `VERIDRA_ENV=operator`.

The scheduler now takes an explicit entitlement-enforcement boundary and `run_service_tick()` enables it only for `VERIDRA_ENV=production`.

Regression evidence:

- `tests/test_monitoring_service.py::test_operator_scheduler_ignores_hosted_plan_entitlements`;
- CI Windows/operator Playwright acceptance in run `36990700714`.

## What H1 does not prove

H1 does not prove:

- real Stripe provider lifecycle;
- real SMTP delivery;
- actual public HTTPS host behavior;
- backup/provider reconciliation on a live host;
- hosted customer usability;
- commercial pricing acceptance.

Those remain H6/H7 or business decisions.

## Next phase

**H2 — Commercial UX and report polish**

Primary first target: entitlement-aware UX.

Users should see recoverable locked/upgrade states instead of raw commercial 403/429 responses where a normal product action can explain the limitation or path forward.
