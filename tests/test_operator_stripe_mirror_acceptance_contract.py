from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT / "tools" / "operator_stripe_mirror_acceptance.py"
).read_text(encoding="utf-8")


def test_stripe_mirror_uses_operator_loopback_auto_login() -> None:
    assert 'page.goto(f"{BASE_URL}/agency", wait_until="networkidle")' in SCRIPT
    assert "Expected loopback auto-login" in SCRIPT
    assert "/api/auth/login" not in SCRIPT
    assert "Workspace slug" not in SCRIPT
    assert "VERIDRA email" not in SCRIPT
    assert "VERIDRA password" not in SCRIPT
    assert "CREDENTIAL_FILE" not in SCRIPT
    assert "--reset-credentials" not in SCRIPT


def test_stripe_mirror_tracks_current_manual_prospect_ui_contract() -> None:
    assert 'get_by_label("Business type")' in SCRIPT
    assert 'get_by_label("Location")' in SCRIPT
    assert 'get_by_label("Why is this business worth reviewing?")' in SCRIPT
    assert 'filter(has_text="Qualification")' in SCRIPT
    assert 'get_by_label("Sector")' not in SCRIPT
    assert 'get_by_label("Locality")' not in SCRIPT
    assert 'get_by_label("Administrative area")' not in SCRIPT
    assert 'get_by_label("Country code")' not in SCRIPT
    assert 'get_by_label("Evidence / discovery note")' not in SCRIPT
