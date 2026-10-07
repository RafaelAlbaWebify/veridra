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


def test_visual_acceptance_checks_semantic_guidance_on_core_screens() -> None:
    assert "CORE_GUIDANCE" in VISUAL
    assert "_assert_semantic_guidance(name, visible)" in VISUAL
    assert ".semantic.json" in VISUAL
    for checkpoint in (
        "core-01-operator-workspace",
        "core-02-qualified-prospect",
        "core-03-prospect-contacted",
        "core-04-prospect-responded",
        "core-05-prospect-conversation",
        "core-06-proposal-accepted-customer-created",
        "core-07-work-start-gate-open",
        "core-08-customer-active-onboarded",
        "core-09-linked-project",
        "core-10-manual-assessment",
        "core-11-remediation-task",
        "core-12-report-delivery",
        "core-13-autonomous-monitoring",
        "core-14-paid-operator-summary",
        "core-15-restart-persistence",
        "core-16-mutated-after-backup",
        "core-17-restored-state",
        "17-delivery-closed-recurring-accepted",
        "23-recurring-management",
    ):
        assert f'"{checkpoint}"' in VISUAL


def test_progress_visual_checkpoint_opens_the_progress_surface() -> None:
    assert 'monitoring_url.rsplit("/monitoring", 1)[0]' in VISUAL
    assert 'page.goto(f"{project_url}/progress"' in VISUAL
    assert '_capture(page, "15-progress-changes")' in VISUAL


def test_ci_runs_full_lifecycle_visual_acceptance_at_target_resolution() -> None:
    assert 'True Playwright first-customer operator acceptance' in CI
    assert 'VERIDRA_E2E_VIEWPORT_WIDTH: "1920"' in CI
    assert 'VERIDRA_E2E_VIEWPORT_HEIGHT: "1080"' in CI
    assert 'VERIDRA_OPERATOR_E2E_ACCEPTANCE.bat' in CI
    assert 'python tools/operator_visual_acceptance_entry.py' not in CI


NAV = (ROOT / "src" / "veridra" / "agency_navigation.py").read_text(
    encoding="utf-8"
)
RECURRING = (
    ROOT / "src" / "veridra" / "agency_recurring_service_web.py"
).read_text(encoding="utf-8")


def test_workbench_geometry_keeps_padding_inside_viewport() -> None:
    assert "box-sizing:border-box;" in NAV
    assert ".workbench-split>*{min-width:0}" in NAV
    assert ".workbench-pane{" in NAV
    assert "min-width:0;" in NAV
    assert ".agency-workbench input," in NAV
    assert "box-sizing:border-box;" in NAV
    assert "max-width:100%;" in NAV


def test_project_presence_care_uses_workbench_internal_scroll() -> None:
    assert "agency_navigation(identity, current='recurring')" in RECURRING
    assert "class='agency-workbench'" in RECURRING
    assert "class='workbench-body'" in RECURRING
    assert "class='workbench-scroll'" in RECURRING
