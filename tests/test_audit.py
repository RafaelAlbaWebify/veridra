from pathlib import Path

from veridra.audit import run_audit


def test_audit(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    report = run_audit(root, tmp_path)
    assert report["passed"] is True
    assert (tmp_path / "audit-report.json").exists()


def test_trust_findings_are_explicitly_homepage_scoped() -> None:
    from veridra.core import analyze_document

    findings = {
        item.id: item
        for item in analyze_document(
            "<html><body><h1>Practice</h1><a href='/contact'>Contact</a></body></html>",
            {},
        )
    }

    for identifier in ("trust.about", "trust.contact", "trust.privacy", "trust.terms"):
        assert findings[identifier].title.startswith("Homepage ")
        assert findings[identifier].evidence["scope"] == "homepage"

    assert "homepage" in findings["trust.about"].recommendation.lower()
    assert "homepage" in findings["trust.privacy"].recommendation.lower()
    assert "homepage" in findings["trust.terms"].recommendation.lower()
