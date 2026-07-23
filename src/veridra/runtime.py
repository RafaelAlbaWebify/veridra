from __future__ import annotations

from . import app as app_module
from . import public_web
from .app import app as app
from .commercial_web import router as commercial_router
from .crawl_profile_web import router as crawl_profile_router
from .lead_web import router as lead_router
from .monitoring_web import router as monitoring_router
from .pdf_web import router as pdf_router
from .public_web import ToolDefinition
from .task_web import router as task_router
from .workspace_enforcement import enforce_workspace_policy
from .workspace_members_web import router as workspace_members_router
from .workspace_web import router as workspace_router

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
app.include_router(task_router)
app.include_router(lead_router)
app.include_router(pdf_router)
app.include_router(crawl_profile_router)
app.include_router(monitoring_router)
app.include_router(commercial_router)
app.include_router(workspace_router)
app.include_router(workspace_members_router)


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
