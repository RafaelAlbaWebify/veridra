from __future__ import annotations

import os

from fastapi import APIRouter
from fastapi.responses import RedirectResponse

from .runtime_config import local_agency_mode_enabled

router = APIRouter(tags=["landing"])


@router.get("/", response_model=None)
def landing() -> RedirectResponse:
    if (
        os.environ.get("VERIDRA_ENV", "").strip().lower() == "operator"
        or local_agency_mode_enabled()
    ):
        return RedirectResponse("/agency", status_code=302)
    return RedirectResponse("/free", status_code=302)
