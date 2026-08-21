from __future__ import annotations

import shutil
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class AtomicFileLockError(RuntimeError):
    pass


@contextmanager
def exclusive_directory_lock(
    path: Path,
    *,
    timeout_seconds: float = 2.0,
    stale_after_seconds: float = 30.0,
) -> Iterator[None]:
    if timeout_seconds <= 0 or stale_after_seconds <= 0:
        raise ValueError("Filesystem lock timing values must be positive.")
    path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout_seconds
    acquired = False
    while not acquired:
        try:
            path.mkdir()
            acquired = True
        except FileExistsError:
            try:
                age = time.time() - path.stat().st_mtime
                if age > stale_after_seconds:
                    shutil.rmtree(path)
                    continue
            except FileNotFoundError:
                continue
            except OSError as exc:
                raise AtomicFileLockError("Filesystem lock state could not be inspected.") from exc
            if time.monotonic() >= deadline:
                raise AtomicFileLockError("Filesystem lock could not be acquired.") from None
            time.sleep(0.01)
        except OSError as exc:
            raise AtomicFileLockError("Filesystem lock could not be acquired.") from exc
    try:
        yield
    finally:
        if acquired:
            try:
                shutil.rmtree(path)
            except FileNotFoundError:
                pass
            except OSError as exc:
                raise AtomicFileLockError("Filesystem lock could not be released.") from exc
