from __future__ import annotations

from veridra.visual_outreach_regulatory_cli import _is_privacy_link, regulatory_relevance


def test_privacy_link_detection_is_narrow() -> None:
    assert _is_privacy_link("Privacy Policy", "https://clinic.example/privacy-policy")
    assert not _is_privacy_link("Book appointment", "https://clinic.example/book")


def test_irish_privacy_dead_end_gets_regulatory_context() -> None:
    value = regulatory_relevance(
        country_code="IE",
        link_text="Privacy Policy",
        target_url="https://clinic.example/privacy-policy",
        status_code=404,
    )
    assert value is not None
    assert value["jurisdiction"] == "Ireland"
    assert "20,000,000" in str(value["legal_maximum_exposure"])
    assert "4%" in str(value["legal_maximum_exposure"])
    assert "Not responsibly estimable" in str(value["estimated_actual_fine"])


def test_non_irish_or_non_privacy_broken_link_has_no_regulatory_claim() -> None:
    assert regulatory_relevance(
        country_code="ES",
        link_text="Privacy Policy",
        target_url="https://clinic.example/privacy-policy",
        status_code=404,
    ) is None
    assert regulatory_relevance(
        country_code="IE",
        link_text="Book appointment",
        target_url="https://clinic.example/book",
        status_code=404,
    ) is None


def test_no_qualifying_broken_links_skips_browser(monkeypatch, tmp_path) -> None:
    from veridra import visual_outreach_regulatory_cli as module

    def forbidden_browser():
        raise AssertionError("Chromium must not start for empty evidence")

    monkeypatch.setattr(module, "sync_playwright", forbidden_browser)
    rows = [
        {"evidence": [{"issue_type": "missing_alt", "details": {}}]},
        {"evidence": [{"issue_type": "broken_link",
                       "details": {"target_url": "https://example.test",
                                   "status_code": 200},
                       "screenshot_path": "screens/healthy.png"}]},
        {"evidence": []},
    ]
    assert module._augment_rows(
        rows=rows, root=tmp_path, country_code="IE", timeout_ms=20000,
    ) == (0, 0)


def test_qualifying_broken_link_still_captures_and_preserves_regulatory_context(
    monkeypatch, tmp_path,
) -> None:
    from veridra import visual_outreach_regulatory_cli as module

    launches = []
    class Context:
        def new_page(self):
            return object()
        def close(self):
            return None
    class Browser:
        def new_context(self, **kwargs):
            assert kwargs["viewport"]["width"] == 1280
            return Context()
        def close(self):
            return None
    class Chromium:
        def launch(self, *, headless):
            assert headless is True
            launches.append("chromium")
            return Browser()
    class Playwright:
        chromium = Chromium()
    class Session:
        def __enter__(self):
            return Playwright()
        def __exit__(self, *args):
            return None

    monkeypatch.setattr(module, "sync_playwright", lambda: Session())
    monkeypatch.setattr(module, "_safe_routes", lambda context: None)
    monkeypatch.setattr(module, "_goto_and_capture", lambda *args: True)
    issue = {
        "issue_type": "broken_link",
        "details": {
            "target_url": "https://clinic.example/privacy-policy",
            "link_text": "Privacy Policy",
            "status_code": 404,
        },
        "screenshot_path": "screens/privacy.png",
    }
    assert module._augment_rows(
        rows=[{"evidence": [issue]}], root=tmp_path,
        country_code="IE", timeout_ms=20000,
    ) == (1, 1)
    assert launches == ["chromium"]
    assert issue["destination_screenshot_path"] == "screens/privacy-result.png"
    assert isinstance(issue["regulatory_relevance"], dict)
