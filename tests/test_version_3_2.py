from __future__ import annotations

from pathlib import Path


def test_release_notes_preserve_3_2_0_history() -> None:
    release = Path("docs/releases/3.2.0.md")
    assert release.exists()
    assert "3.2.0" in release.read_text(encoding="utf-8")
