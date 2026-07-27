from __future__ import annotations

from fastapi import FastAPI
from fastapi.routing import APIRoute
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.routing import BaseRoute

from . import app as app_module
from . import public_web
from .agency_conversion_web import router as agency_conversion_router
from .agency_lead_web import router as agency_lead_router
from .agency_monitoring_web import router as agency_monitoring_router
from .agency_project_index_web import router as agency_project_index_router
from .agency_report_profile_web import router as agency_report_profile_router
from .agency_report_web import router as agency_report_router
from .agency_task_web import router as agency_task_router
from .agency_workflow_web import router as agency_workflow_router
from .application_identity import configure_identity_middleware
from .assessment_project_conversion_api import router as assessment_project_conversion_router
from .auth_api import router as auth_router
from .crawl_profile_web import router as crawl_profile_router
from .existing_user_invitation_api import router as existing_user_invitation_router
from .finding_task_api import router as finding_task_router
from .invitation_api import router as invitation_router
from .lead_form_tenant_binding_api import router as lead_form_tenant_binding_router
from .lead_project_conversion_api import router as lead_project_conversion_router
from .member_assignments_web import router as member_assignments_router
from .monitoring_job_api import router as monitoring_job_router
from .onboarding_web import router as onboarding_router
from .operations_api import router as operations_router
from .password_recovery_api import router as password_recovery_router
from .pdf_web import router as pdf_router
from .public_web import ToolDefinition
from .runtime_boundary import RuntimeBoundaryMiddleware
from .runtime_config import RuntimeConfig
from .runtime_route_policy import is_legacy_browser_route
from .session_api import router as session_router
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
from .version import __version__
from .workspace_enforcement import enforce_workspace_policy
from .workspace_members_web import router as workspace_members_router
from .workspace_web import router as workspace_router

_REPLACED_ASSESSMENT_PATHS = {"/", "/api/assess", "/report", "/export"}


def _approved_base_route(route: BaseRoute) -> bool:
    if is_legacy_browser_route(route):
        return False
    if isinstance(route, APIRoute):
        methods = route.methods or set()
        if route.path in _REPLACED_ASSESSMENT_PATHS and "GET" in methods:
            return False
    return True


app = FastAPI(title="Veridra", version=__version__)
app.router.routes.extend(
    route for route in app_module.app.router.routes if _approved_base_route(route)
)

runtime_config = RuntimeConfig.from_environment()
runtime_config.configure_directories()
app.state.veridra_runtime_config = runtime_config
if runtime_config.tenant_data_root is not None:
    app.state.veridra_tenant_data_root = runtime_config.tenant_data_root
app.add_middleware(
    RuntimeBoundaryMiddleware,
    max_body_bytes=runtime_config.max_request_body_bytes,
    trusted_proxy_ips=runtime_config.trusted_proxy_ips,
)
if runtime_config.allowed_hosts:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(runtime_config.allowed_hosts))

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
app.include_router(onboarding_router)
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
app.include_router(workspace_members_router)
app.include_router(member_assignments_router)
app.include_router(agency_workflow_router)
app.include_router(agency_project_index_router)
app.include_router(agency_conversion_router)
app.include_router(agency_lead_router)
app.include_router(agency_task_router)
app.include_router(agency_monitoring_router)
app.include_router(agency_report_profile_router)
app.include_router(agency_report_router)


def main() -> None:
    import uvicorn

    uvicorn.run(
        app,
        host=runtime_config.bind_host,
        port=runtime_config.bind_port,
        proxy_headers=False,
    )
