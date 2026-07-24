from __future__ import annotations

import veridra
from veridra.version import __version__


def test_version_metadata_is_aligned_for_3_3_0() -> None:
    assert __version__ == "3.3.0"
    assert veridra.__version__ == __version__
