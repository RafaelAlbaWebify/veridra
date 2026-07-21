from __future__ import annotations

from .app import app as app
from .task_web import router as task_router

app.include_router(task_router)


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
