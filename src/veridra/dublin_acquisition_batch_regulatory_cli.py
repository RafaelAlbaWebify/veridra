from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import cast

from . import dublin_acquisition_batch_resilient_cli as base
from .visual_outreach_regulatory_cli import run as regulatory_visual_run

RunFunction = Callable[[Sequence[str] | None], int]


def _visual_run(argv: Sequence[str] | None = None) -> int:
    values = list(argv or [])
    values.extend(["--country-code", "IE"])
    return regulatory_visual_run(values)


def run(argv: Sequence[str] | None = None) -> int:
    original = cast(RunFunction, getattr(base, "visual_run"))
    setattr(base, "visual_run", _visual_run)
    try:
        return base.run(argv)
    finally:
        setattr(base, "visual_run", original)


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
