from __future__ import annotations

from collections.abc import Sequence

from . import dublin_acquisition_batch_resilient_cli as base
from .visual_outreach_hardened_cli import run as hardened_visual_run


def _visual_run(argv: Sequence[str] | None = None) -> int:
    values = list(argv or [])
    values.extend(["--country-code", "IE"])
    return hardened_visual_run(values)


def run(argv: Sequence[str] | None = None) -> int:
    original = base.visual_run  # type: ignore[attr-defined]
    base.visual_run = _visual_run  # type: ignore[attr-defined]
    try:
        return base.run(argv)
    finally:
        base.visual_run = original  # type: ignore[attr-defined]


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
