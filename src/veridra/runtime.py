from __future__ import annotations

from .app import app as app
from .crawl_profile_web import router as crawl_profile_router
from .lead_web import router as lead_router
from .pdf_web import router as pdf_router
from .task_web import router as task_router

app.include_router(task_router)
app.include_router(lead_router)
app.include_router(pdf_router)
app.include_router(crawl_profile_router)


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
