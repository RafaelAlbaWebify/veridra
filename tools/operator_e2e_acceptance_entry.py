from __future__ import annotations

import subprocess
import tempfile
import uuid
from pathlib import Path

import operator_e2e_acceptance as acceptance


def _run_launcher(repo: Path, env: dict[str, str], command: str, *args: str) -> str:
    """Run the Windows launcher without PIPE handles inherited by long-lived children."""
    script = repo / "scripts" / "windows" / "veridra-local.ps1"
    print(f"[E2E] launcher {command}: start", flush=True)

    # Long-lived VERIDRA child processes can briefly retain inherited Windows file
    # handles after PowerShell exits. Keep launcher logs in the system temp directory
    # instead of synchronously deleting a TemporaryDirectory and racing those handles.
    output_path = (
        Path(tempfile.gettempdir())
        / f"veridra-launcher-{uuid.uuid4().hex}-{command}.log"
    )
    with output_path.open("w+", encoding="utf-8") as output:
        completed = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script),
                command,
                *args,
            ],
            cwd=repo,
            env=env,
            stdout=output,
            stderr=subprocess.STDOUT,
            timeout=180,
            check=False,
        )
        output.flush()
        output.seek(0)
        text = output.read()

    print(f"[E2E] launcher {command}: exit {completed.returncode}", flush=True)
    if text:
        print(text.rstrip(), flush=True)
    if completed.returncode != 0:
        raise RuntimeError(
            f"VERIDRA launcher {command!r} failed ({completed.returncode}):\n{text}"
        )
    return text


acceptance._run_launcher = _run_launcher


if __name__ == "__main__":
    acceptance.main()
