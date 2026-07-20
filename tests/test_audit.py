from pathlib import Path

from veridra.audit import run_audit


def test_audit(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    report = run_audit(root, tmp_path)
    assert report["passed"] is True
    assert (tmp_path / "audit-report.json").exists()
