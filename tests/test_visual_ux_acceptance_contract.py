from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VISUAL = (ROOT / "tools" / "operator_visual_acceptance_entry.py").read_text(
    encoding="utf-8"
)
OPERATOR = (ROOT / "tools" / "operator_e2e_acceptance.py").read_text(
    encoding="utf-8"
)
CI = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")


def test_operator_viewport_is_configurable_without_changing_default() -> None:
    assert 'VERIDRA_E2E_VIEWPORT_WIDTH' in OPERATOR
    assert 'VERIDRA_E2E_VIEWPORT_HEIGHT' in OPERATOR
    assert '"1440"' in OPERATOR
    assert '"1000"' in OPERATOR


def test_visual_acceptance_captures_viewport_full_page_and_layout_metrics() -> None:
    assert 'full_page=False' in VISUAL
    assert 'full_page=True' in VISUAL
    assert 'clippedInteractive' in VISUAL
    assert 'internalScrollers' in VISUAL
    assert '.layout.json' in VISUAL


def test_ci_runs_visual_acceptance_at_target_desktop_resolution() -> None:
    assert '1920x1080 visual UX acceptance' in CI
    assert 'VERIDRA_E2E_VIEWPORT_WIDTH: "1920"' in CI
    assert 'VERIDRA_E2E_VIEWPORT_HEIGHT: "1080"' in CI
    assert 'python tools/operator_visual_acceptance_entry.py' in CI
