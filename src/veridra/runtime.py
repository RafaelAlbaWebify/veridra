from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .access_logging import StructuredAccessLogMiddleware, configure_access_logger
from .agency_ai_review_web import router as agency_ai_review_router
from .agency_change_request_transition_web import (
    router as agency_change_request_transition_router,
)
from .agency_change_request_web import router as agency_change_request_router
from .agency_commercial_dashboard_web import router as agency_commercial_dashboard_router
from .agency_conversion_web import completed_agency_audit
from .agency_conversion_web import router as agency_conversion_router
from .agency_crawl_profile_web import router as agency_crawl_profile_router
from .agency_customer_project_web import router as agency_customer_project_router
from .agency_customer_web import router as agency_customer_router
from .agency_deal_index_web import router as agency_deal_index_router
from .agency_deal_web import router as agency_deal_router
from .agency_lead_form_web import router as agency_lead_form_router
from .agency_lead_web import router as agency_lead_router
from .agency_monitoring_web import router as agency_monitoring_router
from .agency_progress_web import router as agency_progress_router
from .agency_project_customer_web import router as agency_project_customer_router
from .agency_project_index_web import router as agency_project_index_router
from .agency_proposal_artifact_web import router as agency_proposal_artifact_router
from .agency_proposal_transition_web import router as agency_proposal_transition_router
from .agency_prospect_discovery_evidence_web import (
    router as agency_prospect_discovery_evidence_router,
)
from .agency_prospect_discovery_web import router as agency_prospect_discovery_router
from .agency_prospect_import_web import router as agency_prospect_import_router
from .agency_prospect_web import router as agency_prospect_router
from .agency_recurring_service_web import router as agency_recurring_service_router
from .agency_reply_transition_web import router as agency_reply_transition_router
from .agency_report_profile_edit_web import router as agency_report_profile_edit_router
from .agency_report_profile_web import router as agency_report_profile_router
from .agency_report_web import router as agency_report_router
from .agency_task_management_web import router as agency_task_management_router
from .agency_task_web import router as agency_task_router
from .agency_workflow_web import router as agency_workflow_router
from .application_identity import configure_identity_middleware
from .assessment_project_conversion_api import router as assessment_project_conversion_router
from .crawl_job_api import router as crawl_job_router
from .crawl_profile_web import router as crawl_profile_router
from .finding_task_api import router as finding_task_router
from .health_web import router as health_router
from .landing_web import router as landing_router
from .lead_form_tenant_binding_api import router as lead_form_tenant_binding_router
from .lead_project_conversion_api import router as lead_project_conversion_router
from .monitoring_job_api import router as monitoring_job_router
from .operations_api import router as operations_router
from .pdf_web import router as pdf_router
from .runtime_boundary import RuntimeBoundaryMiddleware
from .runtime_config import RuntimeConfig, RuntimeEnvironment
from .runtime_email import configure_runtime_email
from .runtime_legal import configure_runtime_legal
from .runtime_route_policy import conceal_operator_excluded_routes
from .security_headers import SecurityHeadersMiddleware
from .tenant_assessment_routes import router as tenant_assessment_router
from .tenant_bound_lead_capture import router as tenant_bound_lead_capture_router
from .tenant_history_api import router as tenant_history_router
from .tenant_lead_api import router as tenant_lead_router
from .tenant_lead_form_api import router as tenant_lead_form_router
from .tenant_monitoring_api import router as tenant_monitoring_router
from .tenant_profile_api import router as tenant_profile_router
from .tenant_project_api import router as tenant_project_router
from .tenant_prospect_api import router as tenant_prospect_router
from .tenant_report_api import router as tenant_report_router
from .tenant_task_api import router as tenant_task_router
from .version import __version__

app = FastAPI(title="Veridra", version=__version__)

runtime_config = RuntimeConfig.from_environment()
runtime_config.configure_directories()
app.state.veridra_runtime_config = runtime_config
if runtime_config.tenant_data_root is not None:
    app.state.veridra_tenant_data_root = runtime_config.tenant_data_root
configure_runtime_legal(app, runtime_config)
configure_runtime_email(app, runtime_config)
operator_mode = runtime_config.environment is RuntimeEnvironment.operator
local_agency_mode = runtime_config.local_agency
webify_workflows = operator_mode or local_agency_mode

app.add_middleware(
    RuntimeBoundaryMiddleware,
    max_body_bytes=runtime_config.max_request_body_bytes,
    trusted_proxy_ips=runtime_config.trusted_proxy_ips,
    hide_schema_routes=(
        runtime_config.environment
        in {RuntimeEnvironment.operator, RuntimeEnvironment.production}
    ),
)
if runtime_config.allowed_hosts:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(runtime_config.allowed_hosts))
app.add_middleware(
    SecurityHeadersMiddleware,
    environment=runtime_config.environment,
)
configure_access_logger()
app.add_middleware(StructuredAccessLogMiddleware)

configure_identity_middleware(app)
app.include_router(health_router)
app.include_router(landing_router)

# Core operator/runtime surfaces.
if not operator_mode:
    app.include_router(tenant_assessment_router)
app.include_router(operations_router)
app.include_router(tenant_project_router)
if not operator_mode:
    app.include_router(assessment_project_conversion_router)
    app.include_router(crawl_job_router)
app.include_router(tenant_history_router)
app.include_router(tenant_report_router)
app.include_router(tenant_prospect_router)
app.include_router(tenant_task_router)
app.include_router(finding_task_router)
app.include_router(tenant_monitoring_router)
app.include_router(monitoring_job_router)
app.include_router(tenant_profile_router)
if not operator_mode:
    app.include_router(pdf_router)
    app.include_router(crawl_profile_router)

# Hosted SaaS account, plan, team and workspace routes permanently retired.
# Only Webify's private operator/customer workflow is supported.

# Local Webify inbound capture stays independent from the retired public SaaS routes.
if not operator_mode:
    app.include_router(tenant_lead_router)
    app.include_router(lead_project_conversion_router)
    app.include_router(tenant_lead_form_router)
    app.include_router(lead_form_tenant_binding_router)
    app.include_router(tenant_bound_lead_capture_router)

# Shared agency workflow. Webify's local-agency mode deliberately combines the proven
# delivery/lead tooling with the existing prospecting, sales and customer lifecycle.
app.include_router(agency_workflow_router)
if webify_workflows:
    # The wrapper routers precede their base routers so they can add or tighten operator
    # actions without duplicating the established pages.
    app.include_router(agency_customer_project_router)
    app.include_router(agency_customer_router)
app.include_router(agency_project_index_router)
if webify_workflows:
    app.include_router(agency_project_customer_router)
    app.include_router(agency_recurring_service_router)
if operator_mode:
    app.add_api_route(
        "/agency/audit",
        completed_agency_audit,
        methods=["GET"],
        response_class=HTMLResponse,
        tags=["agency-conversion"],
    )
else:
    app.include_router(agency_conversion_router)
app.include_router(agency_crawl_profile_router)
if webify_workflows:
    app.include_router(agency_commercial_dashboard_router)
    app.include_router(agency_prospect_import_router)
    app.include_router(agency_prospect_discovery_router)
    app.include_router(agency_prospect_discovery_evidence_router)
    app.include_router(agency_deal_index_router)
    app.include_router(agency_reply_transition_router)
    app.include_router(agency_proposal_transition_router)
    app.include_router(agency_deal_router)
    app.include_router(agency_proposal_artifact_router)
    app.include_router(agency_change_request_transition_router)
    app.include_router(agency_change_request_router)
    app.include_router(agency_prospect_router)
app.include_router(agency_task_router)
app.include_router(agency_task_management_router)
app.include_router(agency_monitoring_router)
app.include_router(agency_progress_router)
app.include_router(agency_ai_review_router)
app.include_router(agency_report_profile_router)
app.include_router(agency_report_profile_edit_router)
app.include_router(agency_report_router)

if not operator_mode:
    app.include_router(agency_lead_router)
    app.include_router(agency_lead_form_router)
else:
    conceal_operator_excluded_routes(app.router.routes)


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
