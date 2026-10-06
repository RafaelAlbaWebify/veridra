from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (
    ROOT / "src" / "veridra" / "agency_customer_project_web.py"
).read_text(encoding="utf-8")


def test_customer_project_section_is_injected_inside_workbench_scroll() -> None:
    assert 'workbench_marker = "</div></section></div></main></body></html>"' in SOURCE
    assert "section + workbench_marker" in SOURCE
