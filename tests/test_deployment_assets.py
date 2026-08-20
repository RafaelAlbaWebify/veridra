from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_docker_image_drops_root_and_installs_browser_runtime() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "FROM python:3.11-slim-bookworm" in dockerfile
    assert "python -m playwright install --with-deps chromium" in dockerfile
    assert "PLAYWRIGHT_BROWSERS_PATH=/ms-playwright" in dockerfile
    assert "USER veridra" in dockerfile
    assert 'CMD ["veridra-api"]' in dockerfile
    assert "VERIDRA_STRIPE_SECRET_KEY" not in dockerfile
    assert "VERIDRA_SMTP_PASSWORD" not in dockerfile


def test_docker_context_excludes_local_state_and_secret_files() -> None:
    ignored = {
        line.strip()
        for line in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.strip()
    }

    assert ".git" in ignored
    assert ".env" in ignored
    assert ".env.*" in ignored
    assert "backups" in ignored
    assert "artifacts" in ignored
    assert "tests" in ignored
    assert "*.bat" in ignored
