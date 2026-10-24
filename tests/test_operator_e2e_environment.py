from __future__ import annotations

from tools.operator_e2e_acceptance import _isolated_operator_environment


def test_e2e_operator_environment_excludes_inherited_local_agency() -> None:
    source = {
        "VERIDRA_ENV": "production",
        "VERIDRA_LOCAL_AGENCY": "1",
        "PATH": "example",
    }

    isolated = _isolated_operator_environment(source)

    assert "VERIDRA_LOCAL_AGENCY" not in isolated
    assert isolated["PATH"] == "example"
    assert source["VERIDRA_LOCAL_AGENCY"] == "1"


def test_e2e_operator_environment_does_not_require_local_agency_flag() -> None:
    source = {"PATH": "example"}

    assert _isolated_operator_environment(source) == source
