from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from veridra.plans_web import router
from veridra.workspace_policy import PLAN_CATALOGUE, PlanName


def test_public_plans_render_enforced_catalogue_without_invented_paid_prices() -> None:
    app = FastAPI()
    app.include_router(router)
    response = TestClient(app).get("/plans")

    assert response.status_code == 200
    for plan in PlanName:
        entitlements = PLAN_CATALOGUE[plan]
        assert f"data-plan='{plan.value}'" in response.text
        assert f"{entitlements.monthly_audits:,}" in response.text
        assert f"{entitlements.max_projects:,}" in response.text
        assert f"{entitlements.max_users:,}" in response.text
    assert "Free workspace · no payment required." in response.text
    assert "configured Stripe price" in response.text
    assert "href='/signup'" in response.text
    assert "href='/login'" in response.text
