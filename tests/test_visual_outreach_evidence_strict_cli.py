from __future__ import annotations

from veridra.visual_outreach_evidence_strict_cli import _html_summary, _safe_stem


def test_safe_stem_is_bounded() -> None:
    value = _safe_stem("Clinic & Dental / Dublin")
    assert value == "Clinic-Dental-Dublin"
    assert len(_safe_stem("x" * 200)) <= 72


def test_strict_summary_is_plain_language() -> None:
    output = _html_summary(
        [
            {
                "business_name": "Clinic A",
                "evidence": [
                    {
                        "screenshot_path": "01-Clinic-A/01-dead-end.png",
                        "what_we_noticed": "The visible link ‘Book now’ leads to a page that does not work.",
                        "why_it_matters": "A visitor can hit a dead end while trying to continue through the website.",
                        "page_url": "https://clinic.example/",
                    }
                ],
            }
        ]
    )
    assert "Book now" in output
    assert "01-Clinic-A/01-dead-end.png" in output
    assert "Content-Security-Policy" not in output
    assert "aria-label" not in output


def test_strict_summary_marks_no_visual_issue() -> None:
    output = _html_summary([{"business_name": "Clinic B", "evidence": []}])
    assert "No strong screenshot-ready issue captured." in output
