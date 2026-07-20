from __future__ import annotations

from importlib.metadata import version

from veridra.app import app
from veridra.version import __version__


def test_application_and_package_versions_match() -> None:
    assert app.version == __version__
    assert version("veridra") == __version__
