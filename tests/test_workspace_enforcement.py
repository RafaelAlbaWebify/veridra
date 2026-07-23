from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from fastapi.testclient import TestClient

from veridra.project_store import ClientProject, ProjectStore
from veridra.workspace_enforcement import enforce_workspace_policy
from veridra.workspace_policy import (
    PlanName,
    UsageKind,
    UsageLedger,
    WorkspaceConfig,
    WorkspaceStore,
)


def _app() -> FastAPI:
    app = FastAPI()
    app.middleware("http")(enforce_workspace_policy)

    @app.post("/projects")
    def projects() -> PlainTextResponse:
        return PlainTextResponse("saved")

    @app.post("/profiles")
    def profiles() -> PlainTextResponse:
        return PlainTextResponse("saved")

    @app.post("/lead-forms")
    def forms() -> PlainTextResponse:
        return PlainTextResponse("saved")

    @app.post("/embed/audit/{form_id}")
    def submit(form_id: str) -> PlainTextResponse:
        return PlainTextResponse(form_id)

    @app.post("/monitoring/run-due")
    def monitoring() -> PlainTextResponse:
        return PlainTextResponse("run")

    @app.get("/report.pdf")
    def pdf() -> PlainTextResponse:
        return PlainTextResponse("pdf")

    @app.get("/free/security")
    def free_tool() -> PlainTextResponse:
        return PlainTextResponse("free")

    return app


def _activate(tmp_path: Path, plan: PlanName) -> None:
    WorkspaceStore(tmp_path / "workspace").save(WorkspaceConfig(plan=plan))


def test_policy_inactive_preserves_existing_routes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VERIDRA_DATA_DIR", str(tmp_path))
    assert TestClient(_app()).post("/profiles").status_code == 200


def test_free_plan_blocks_commercial_features_and_project_overage(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("VERIDRA_DATA_DIR", str(tmp_path))
    _activate(tmp_path, PlanName.free)
    ProjectStore().save(ClientProject.build(name="One", target_url="https://example.com"))
    client = TestClient(_app())

    assert client.post("/projects").status_code == 429
    assert client.post("/profiles").status_code == 403
    assert client.post("/lead-forms").status_code == 403
    assert client.post("/embed/audit/" + "a" * 24).status_code == 403


def test_agency_plan_records_successful_commercial_usage(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VERIDRA_DATA_DIR", str(tmp_path))
    _activate(tmp_path, PlanName.agency)
    client = TestClient(_app())

    assert client.post("/embed/audit/" + "a" * 24).status_code == 200
    assert client.post("/monitoring/run-due").status_code == 200
    assert client.get("/report.pdf?url=https://example.com").status_code == 200

    totals = UsageLedger().totals(
        __import__("veridra.workspace_policy", fromlist=["usage_period"]).usage_period(
            WorkspaceStore().load()
        )
    )
    assert totals[UsageKind.lead_submission] == 1
    assert totals[UsageKind.monitoring_run] == 1
    assert totals[UsageKind.pdf] == 1


def test_free_tools_are_isolated_from_workspace_metering(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VERIDRA_DATA_DIR", str(tmp_path))
    _activate(tmp_path, PlanName.free)
    client = TestClient(_app())

    assert client.get("/free/security").status_code == 200
    assert UsageLedger().list() == []
