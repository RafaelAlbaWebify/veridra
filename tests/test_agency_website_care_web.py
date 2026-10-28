import json
from pathlib import Path

from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from veridra.agency_website_care_web import router
from veridra.website_care_evidence import import_evidence


def test_operator_history_opt_in_and_escaped(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    monkeypatch.delenv("VERIDRA_WEBSITE_CARE_DB", raising=False)
    result = client.get("/agency/website-care/history")
    assert result.status_code == 200
    assert "not configured" in result.text

    data = {
        "contract": "webify_wordpress_care_cycle_v1",
        "passed": True,
        "started_utc": "2026-10-27T15:25:46+00:00",
        "finished_utc": "2026-10-27T15:27:11+00:00",
        "steps": {"inspect": "PASS", "backup": "PASS", "isolated_restore": "PASS"},
    }
    evidence = tmp_path / "evidence.json"
    evidence.write_text(json.dumps(data), encoding="utf-8")
    db = tmp_path / "care.sqlite"
    assert import_evidence(evidence, db, "<lab-site>", "wordpress")
    monkeypatch.setenv("VERIDRA_WEBSITE_CARE_DB", str(db))
    result = client.get("/agency/website-care/history")
    assert result.status_code == 200
    assert "&lt;lab-site&gt;" in result.text
    assert "<lab-site>" not in result.text
    assert "PASS" in result.text


def test_unavailable_ledger_is_non_destructive(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)
    db = tmp_path / "missing.sqlite"
    monkeypatch.setenv("VERIDRA_WEBSITE_CARE_DB", str(db))
    client = TestClient(app)
    result = client.get("/agency/website-care/history")
    assert result.status_code == 200
    assert "No validated" in result.text
    assert not db.exists()
