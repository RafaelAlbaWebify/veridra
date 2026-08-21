from __future__ import annotations

from fastapi import FastAPI
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import app as app_module
from . import public_web
from .access_logging import StructuredAccessLogMiddleware, configure_access_logger
from .agency_conversion_web import router as agency_conversion_router
from .agency_crawl_profile_web import router as agency_crawl_profile_router
from .agency_lead_form_web import router as agency_lead_form_router
from .agency_lead_web import router as agency_lead_router
from .agency_monitoring_web import router as agency_monitoring_router
from .agency_project_index_web import router as agency_project_index_router
from .agency_report_profile_edit_web import router as agency_report_profile_edit_router
from .agency_report_profile_web import router as agency_report_profile_router
from .agency_report_web import router as agency_report_router
from .agency_task_management_web import router as agency_task_management_router
from .agency_task_web import router as agency_task_router
from .agency_workflow_web import router as agency_workflow_router
from .application_identity import configure_identity_middleware
from .assessment_project_conversion_api import router as assessment_project_conversion_router
from .auth_api import router as auth_router
from .browser_auth_web import router as browser_auth_router
from .crawl_profile_web import router as crawl_profile_router
from .existing_user_invitation_api import router as existing_user_invitation_router
from .finding_task_api import router as finding_task_router
from .health_web import router as health_router
from .invitation_api import router as invitation_router
from .invitation_web import router as invitation_web_router
from .landing_web import router as landing_router
from .lead_form_tenant_binding_api import router as lead_form_tenant_binding_router
from .lead_project_conversion_api import router as lead_project_conversion_router
from .member_assignments_web import router as member_assignments_router
from .monitoring_job_api import router as monitoring_job_router
from .onboarding_web import router as onboarding_router
from .operations_api import router as operations_router
from .password_recovery_api import router as password_recovery_router
from .pdf_web import router as pdf_router
from .public_web import ToolDefinition
from .public_web import router as public_router
from .runtime_billing import configure_runtime_billing
from .runtime_boundary import RuntimeBoundaryMiddleware
from .runtime_config import RuntimeConfig
from .runtime_email import configure_runtime_email
from .security_headers import SecurityHeadersMiddleware
from .session_api import router as session_router
from .signup_web import router as signup_router
from .stripe_billing_web import router as stripe_billing_router
from .tenant_assessment_routes import router as tenant_assessment_router
from .tenant_bound_lead_capture import router as tenant_bound_lead_capture_router
from .tenant_history_api import router as tenant_history_router
from .tenant_lead_api import router as tenant_lead_router
from .tenant_lead_form_api import router as tenant_lead_form_router
from .tenant_monitoring_api import router as tenant_monitoring_router
from .tenant_profile_api import router as tenant_profile_router
from .tenant_project_api import router as tenant_project_router
from .tenant_report_api import router as tenant_report_router
from .tenant_task_api import router as tenant_task_router
from .tenant_team_web import router as tenant_team_router
from .version import __version__
from .workspace_enforcement import enforce_workspace_policy
from .workspace_members_web import router as workspace_members_router
from .workspace_web import router as workspace_router

app = FastAPI(title="Veridra", version=__version__)

runtime_config = RuntimeConfig.from_environment()
runtime_config.configure_directories()
app.state.veridra_runtime_config = runtime_config
if runtime_config.tenant_data_root is not None:
    app.state.veridra_tenant_data_root = runtime_config.tenant_data_root
configure_runtime_email(app, runtime_config)
configure_runtime_billing(app, runtime_config)
app.add_middleware(
    RuntimeBoundaryMiddleware,
    max_body_bytes=runtime_config.max_request_body_bytes,
    trusted_proxy_ips=runtime_config.trusted_proxy_ips,
)
if runtime_config.allowed_hosts:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(runtime_config.allowed_hosts))
app.add_middleware(
    SecurityHeadersMiddleware,
    environment=runtime_config.environment,
)
configure_access_logger()
app.add_middleware(StructuredAccessLogMiddleware)

if "Accessibility" not in app_module._AREAS:
    vars(app_module)["_AREAS"] = (*app_module._AREAS, "Accessibility")

_ACCESSIBILITY_TOOL = ToolDefinition(
    slug="accessibility",
    title="Accessibility Readiness",
    description=(
        "Check static language, labels, names, heading structure, IDs and image-alt signals."
    ),
    areas=("Accessibility",),
    limitation=(
        "Static HTML heuristics only. This is not WCAG conformance, browser-rendered "
        "testing or assistive-technology validation."
    ),
)
if _ACCESSIBILITY_TOOL.slug not in public_web._TOOL_BY_SLUG:
    vars(public_web)["TOOLS"] = (*public_web.TOOLS, _ACCESSIBILITY_TOOL)
    public_web._TOOL_BY_SLUG[_ACCESSIBILITY_TOOL.slug] = _ACCESSIBILITY_TOOL

app.middleware("http")(enforce_workspace_policy)
configure_identity_middleware(app)
app.include_router(health_router)
app.include_router(landing_router)
app.include_router(public_router)
app.include_router(onboarding_router)
app.include_router(signup_router)
app.include_router(browser_auth_router)
app.include_router(invitation_web_router)
app.include_router(stripe_billing_router)
app.include_router(tenant_assessment_router)
app.include_router(operations_router)
app.include_router(auth_router)
app.include_router(password_recovery_router)
app.include_router(session_router)
app.include_router(invitation_router)
app.include_router(existing_user_invitation_router)
app.include_router(tenant_project_router)
app.include_router(assessment_project_conversion_router)
app.include_router(tenant_history_router)
app.include_router(tenant_report_router)
app.include_router(tenant_lead_router)
app.include_router(lead_project_conversion_router)
app.include_router(tenant_lead_form_router)
app.include_router(tenant_task_router)
app.include_router(finding_task_router)
app.include_router(tenant_monitoring_router)
app.include_router(monitoring_job_router)
app.include_router(tenant_profile_router)
app.include_router(lead_form_tenant_binding_router)
app.include_router(tenant_bound_lead_capture_router)
app.include_router(pdf_router)
app.include_router(crawl_profile_router)
app.include_router(workspace_router)
app.include_router(tenant_team_router)
app.include_router(workspace_members_router)
app.include_router(member_assignments_router)
app.include_router(agency_workflow_router)
app.include_router(agency_project_index_router)
app.include_router(agency_conversion_router)
app.include_router(agency_crawl_profile_router)
app.include_router(agency_lead_router)
app.include_router(agency_lead_form_router)
app.include_router(agency_task_router)
app.include_router(agency_task_management_router)
app.include_router(agency_monitoring_router)
app.include_router(agency_report_profile_router)
app.include_router(agency_report_profile_edit_router)
app.include_router(agency_report_router)


def main() -> None:
    import uvicorn

    uvicorn.run(
        app,
        host=runtime_config.bind_host,
        port=runtime_config.bind_port,
        proxy_headers=False,
        access_log=False,
    )


if __name__ == "__main__":
    main()
