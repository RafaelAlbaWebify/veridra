from veridra import __version__
from veridra.version import __version__ as module_version


def test_release_version_is_3_2_0() -> None:
    assert __version__ == "3.2.0"
    assert module_version == "3.2.0"
