from veridra.agency_ui import agency_design_system, help_tip


def test_agency_design_system_exposes_augur_family_tokens() -> None:
    css = agency_design_system()

    assert "--veridra-canvas:#0b0e12" in css
    assert "--veridra-text:#e8edf2" in css
    assert "--veridra-border:#242a32" in css
    assert "--veridra-success:#7fb48a" in css
    assert ".agency-nav" in css
    assert ".operator-command" in css


def test_help_tip_is_hover_and_keyboard_accessible() -> None:
    tip = help_tip("Explains <evidence> & next action.", label="Evidence")

    assert "class='help-tip'" in tip
    assert "tabindex='0'" in tip
    assert "role='note'" in tip
    assert "data-help='Explains &lt;evidence&gt; &amp; next action.'" in tip
    assert "aria-label='Evidence: Explains &lt;evidence&gt; &amp; next action.'" in tip



def test_workbench_body_does_not_render_as_a_full_height_empty_panel() -> None:
    css = agency_design_system()

    assert ".agency-workbench>section.workbench-body{" in css
    assert "box-shadow:none!important" in css
    assert "align-content:start;" in css


def test_badges_remain_legible_on_dark_operator_theme() -> None:
    css = agency_design_system()

    assert ".badge{" in css
    assert "background:#15232d!important" in css
    assert "color:#c7d7e3!important" in css
