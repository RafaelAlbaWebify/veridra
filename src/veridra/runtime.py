from __future__ import annotations

from .app import app as app
from .lead_web import router as lead_router
from .task_web import router as task_router

app.include_router(task_router)
app.include_router(lead_router)


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
