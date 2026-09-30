from __future__ import annotations

import hashlib
import json
import os
import subprocess
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REQUIRED_STRIPE_PHASES = ("paid", "failed", "recovered", "cancel-pending", "cancelled")
MANUAL_RELEASE_BLOCKERS = (
    "Qualified legal/privacy review of the production customer contract/privacy pack.",
    "Rafael explicit final release/outreach approval under #284/#296.",
)

PRE_CHARGE_GATES = (
    "Complete/confirm WEBIFY LIMITED Stripe live business verification/KYC, payout "
    "and account-security setup before the first real charge.",
    "Determine and record the first real customer's transaction-specific VAT/invoice "
    "treatment before issuing the invoice or taking payment.",
)


def _run(command: list[str], *, cwd: Path, timeout: int = 900) -> tuple[int, str]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )
    return completed.returncode, completed.stdout


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _latest(downloads: Path, pattern: str) -> Path:
    matches = sorted(downloads.glob(pattern), key=lambda path: path.stat().st_mtime)
    if not matches:
        raise FileNotFoundError(f"No evidence matches {pattern}")
    return matches[-1]


def _read_zip_json(path: Path, name: str) -> dict[str, Any]:
    with zipfile.ZipFile(path) as archive:
        raw = archive.read(name)
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path.name}:{name} did not contain a JSON object")
    return payload


def _stripe_pattern(phase: str) -> str:
    # Evidence filenames preserve the phase token exactly, including the hyphen
    # used by cancel-pending.
    return f"VERIDRA_STRIPE_MIRROR_{phase.upper()}_*.zip"


def run() -> Path:
    if os.name != "nt":
        raise SystemExit("Final readiness acceptance must run on Windows.")

    repo = Path(__file__).resolve().parents[1]
    downloads = Path.home() / "Downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    evidence_dir = downloads / f"VERIDRA_FINAL_READINESS_ACCEPTANCE_{stamp}"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    output_zip = evidence_dir.with_suffix(".zip")

    report: dict[str, Any] = {
        "contract": "veridra_final_readiness_acceptance",
        "version": "1.0",
        "started_at": datetime.now(UTC).isoformat(),
        "technical_dry_run_passed": False,
        "production_release_passed": False,
        "manual_release_blockers": list(MANUAL_RELEASE_BLOCKERS),
        "pre_charge_gates": list(PRE_CHARGE_GATES),
        "checks": {},
        "stripe_evidence": {},
    }

    try:
        preflight_code, preflight_output = _run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(repo / "scripts" / "windows" / "veridra-local.ps1"),
                "operator-preflight",
            ],
            cwd=repo,
            timeout=180,
        )
        (evidence_dir / "operator-preflight.txt").write_text(
            preflight_output, encoding="utf-8", errors="replace"
        )
        preflight_json = None
        for line in reversed([line.strip() for line in preflight_output.splitlines()]):
            if not line.startswith("{"):
                continue
            try:
                candidate = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(candidate, dict) and "ready" in candidate and "status" in candidate:
                preflight_json = candidate
                break

        report["operator_preflight"] = {
            "exit_code": preflight_code,
            "result": preflight_json,
        }
        report["checks"]["operator_preflight_ready"] = bool(
            preflight_json and preflight_json.get("ready") is True
        )

        e2e_code, e2e_output = _run(
            ["cmd.exe", "/d", "/c", str(repo / "VERIDRA_OPERATOR_E2E_ACCEPTANCE.bat")],
            cwd=repo,
            timeout=900,
        )
        (evidence_dir / "operator-e2e-console.txt").write_text(
            e2e_output, encoding="utf-8", errors="replace"
        )
        report["checks"]["operator_e2e_exit_zero"] = e2e_code == 0

        e2e_zip = _latest(downloads, "VERIDRA_OPERATOR_E2E_ACCEPTANCE_*.zip")
        e2e_report = _read_zip_json(e2e_zip, "operator-e2e-report.json")
        report["operator_e2e_evidence"] = {
            "file": e2e_zip.name,
            "sha256": _sha256(e2e_zip),
            "passed": bool(e2e_report.get("passed")),
            "checks": e2e_report.get("checks", {}),
        }
        (evidence_dir / "operator-e2e-report.json").write_text(
            json.dumps(e2e_report, indent=2, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        report["checks"]["operator_e2e_report_passed"] = bool(e2e_report.get("passed"))
        report["checks"]["operator_e2e_all_checks_true"] = all(
            bool(value) for value in (e2e_report.get("checks") or {}).values()
        )

        for phase in REQUIRED_STRIPE_PHASES:
            evidence_zip = _latest(downloads, _stripe_pattern(phase))
            phase_report = _read_zip_json(evidence_zip, "report.json")
            phase_ok = (
                phase_report.get("contract") == "veridra_stripe_provider_mirror_acceptance"
                and phase_report.get("phase") == phase
                and phase_report.get("passed") is True
            )
            report["stripe_evidence"][phase] = {
                "file": evidence_zip.name,
                "sha256": _sha256(evidence_zip),
                "passed": phase_ok,
            }
            safe_phase = phase.replace("-", "_")
            (evidence_dir / f"stripe-{safe_phase}-report.json").write_text(
                json.dumps(phase_report, indent=2, ensure_ascii=False, sort_keys=True),
                encoding="utf-8",
            )
            report["checks"][f"stripe_{safe_phase}_evidence_passed"] = phase_ok

        state_file = (
            Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
            / "Veridra"
            / "provider-acceptance"
            / "stripe-mirror.json"
        )
        report["provider_acceptance_state_file"] = str(state_file)
        report["checks"]["provider_acceptance_state_exists"] = state_file.exists()
        if state_file.exists():
            state_payload = json.loads(state_file.read_text(encoding="utf-8"))
            sanitized_state = {
                key: value
                for key, value in state_payload.items()
                if key not in {"password", "password_dpapi"}
            }
            (evidence_dir / "stripe-provider-acceptance-state.json").write_text(
                json.dumps(sanitized_state, indent=2, ensure_ascii=False, sort_keys=True),
                encoding="utf-8",
            )

        report["technical_dry_run_passed"] = all(report["checks"].values())
        report["production_release_passed"] = (
            report["technical_dry_run_passed"] and not report["manual_release_blockers"]
        )
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        report["finished_at"] = datetime.now(UTC).isoformat()
        (evidence_dir / "final-readiness-report.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(evidence_dir.iterdir()):
                archive.write(path, arcname=path.name)

    print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
    print(f"Evidence ZIP: {output_zip}")

    if not report["technical_dry_run_passed"]:
        raise SystemExit(1)
    return output_zip


def main() -> None:
    run()


if __name__ == "__main__":
    main()
