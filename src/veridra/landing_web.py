from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import RedirectResponse

router = APIRouter(tags=["landing"])


@router.get("/", response_model=None)
def landing() -> RedirectResponse:
    return RedirectResponse("/free", status_code=302)
