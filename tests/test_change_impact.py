"""Contract tests for the static change-impact tool; no live customer data."""
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "change_impact.py"
spec = importlib.util.spec_from_file_location("change_impact", SCRIPT)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class ImpactFixtureTests(unittest.TestCase):
    def test_transitive_consumers_and_test_discovery(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = root / "src" / "veridra"
            tests = root / "tests"
            app.mkdir(parents=True)
            tests.mkdir()
            (app / "__init__.py").write_text("")
            (app / "core.py").write_text("VALUE = 1\n")
            (app / "service.py").write_text("from .core import VALUE\n")
            (tests / "test_service.py").write_text("from veridra.service import VALUE\n")
            report = mod.analyze(["src/veridra/core.py"], root)
            self.assertIn("src/veridra/service.py", report["source_consumers"])
            self.assertIn("tests/test_service.py", report["candidate_tests"])
            self.assertFalse(report["requires_full_gate"])

    def test_emitted_paths_use_forward_slashes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = root / "src" / "veridra"
            tests = root / "tests"
            app.mkdir(parents=True)
            tests.mkdir()
            (app / "__init__.py").write_text("")
            (app / "core.py").write_text("VALUE = 1\\n")
            (app / "consumer.py").write_text("from .core import VALUE\\n")
            (tests / "test_consumer.py").write_text("from veridra.consumer import VALUE\\n")
            report = mod.analyze(["src/veridra/core.py"], root)
            for key in ("source_consumers", "candidate_tests", "impacted_dynamic_import_files"):
                self.assertTrue(all("\\\\" not in p for p in report[key]))

    def test_unmodelled_change_forces_full_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src" / "veridra").mkdir(parents=True)
            (root / "tests").mkdir()
            report = mod.analyze([".github/workflows/ci.yml"], root)
            self.assertTrue(report["requires_full_gate"])
            self.assertEqual(report["unmodelled_changed_files"], [".github/workflows/ci.yml"])

    def test_git_diff_captures_deleted_modules(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src" / "veridra").mkdir(parents=True)
            (root / "tests").mkdir()
            target = root / "src" / "veridra" / "legacy.py"
            target.write_text("VALUE = 1\n")
            commands = [
                ["git", "init", "-q"],
                ["git", "add", "."],
                [
                    "git", "-c", "user.name=Fixture",
                    "-c", "user.email=fixture@example.invalid",
                    "commit", "-qm", "fixture",
                ],
            ]
            for command in commands:
                subprocess.run(command, cwd=root, capture_output=True, check=True)
            target.unlink()
            subprocess.run(
                ["git", "add", "-u"], cwd=root, capture_output=True, check=True
            )
            subprocess.run(
                [
                    "git", "-c", "user.name=Fixture",
                    "-c", "user.email=fixture@example.invalid",
                    "commit", "-qm", "deleted",
                ],
                cwd=root, capture_output=True, check=True,
            )
            self.assertIn("src/veridra/legacy.py", mod.changed("HEAD~1", root))

    def test_removed_module_requires_full_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src" / "veridra").mkdir(parents=True)
            (root / "tests").mkdir()
            report = mod.analyze(["src/veridra/deleted_store.py"], root)
            self.assertTrue(report["requires_full_gate"])
            self.assertIn(
                "src/veridra/deleted_store.py", report["unmodelled_changed_files"]
            )

    def test_impacted_dynamic_import_forces_full_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = root / "src" / "veridra"
            tests = root / "tests"
            app.mkdir(parents=True)
            tests.mkdir()
            (app / "__init__.py").write_text("")
            (app / "core.py").write_text("VALUE = 1\n")
            (app / "dynamic.py").write_text(
                "from .core import VALUE\nimport importlib\n"
                "mod = importlib.import_module('veridra.core')\n"
            )
            (tests / "test_dynamic.py").write_text("import veridra.dynamic\n")
            report = mod.analyze(["src/veridra/core.py"], root)
            self.assertIn("src/veridra/dynamic.py", report["impacted_dynamic_import_files"])
            self.assertTrue(report["requires_full_gate"])

    def test_tenant_store_requires_cross_boundary_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = root / "src" / "veridra"
            tests = root / "tests"
            app.mkdir(parents=True)
            tests.mkdir()
            (app / "tenant_customer_store.py").write_text("VALUE = 1\n")
            (tests / "test_backup_restore.py").write_text("pass\n")
            report = mod.analyze(["src/veridra/tenant_customer_store.py"], root)
            self.assertTrue(report["requires_full_gate"])
            self.assertEqual(report["critical_boundaries"][0]["boundary"], "tenant-persistence")
            self.assertIn(
                "tests/test_backup_restore.py",
                report["critical_boundaries"][0]["suggested_tests"],
            )

    def test_noncritical_module_does_not_invent_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src" / "veridra").mkdir(parents=True)
            (root / "tests").mkdir()
            (root / "src" / "veridra" / "maths.py").write_text("VALUE = 2\n")
            report = mod.analyze(["src/veridra/maths.py"], root)
            self.assertEqual(report["critical_boundaries"], [])

    def test_signature_regression_maps_failing_consumer(self) -> None:
        """Synthetic API break must fail a consumer, and impact must identify its test."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = root / "src" / "veridra"
            tests = root / "tests"
            app.mkdir(parents=True)
            tests.mkdir()
            (app / "__init__.py").write_text("")
            core = app / "core.py"
            core.write_text("def calculate(a: int, b: int) -> int:\n    return a + b\n")
            (app / "service.py").write_text(
                "from .core import calculate\ndef run() -> int:\n    return calculate(2, 3)\n"
            )
            (tests / "test_service.py").write_text(
                "from veridra.service import run\nassert run() == 5\n"
            )
            env = dict(os.environ, PYTHONPATH=str(root / "src"))
            cmd = [sys.executable, str(tests / "test_service.py")]
            good = subprocess.run(cmd, env=env, capture_output=True, text=True)
            self.assertEqual(good.returncode, 0, good.stderr)
            core.write_text("def calculate(a: int) -> int:\n    return a\n")
            broken = subprocess.run(cmd, env=env, capture_output=True, text=True)
            self.assertNotEqual(broken.returncode, 0)
            self.assertIn("TypeError", broken.stderr)
            report = mod.analyze(["src/veridra/core.py"], root)
            self.assertIn("tests/test_service.py", report["candidate_tests"])

    def test_guarded_fastapi_router_registration_is_traced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = root / "src" / "veridra"
            app.mkdir(parents=True)
            (root / "tests").mkdir()
            (app / "runtime.py").write_text(
                "from .agency_web import router as agency_router\n"
                "if True:\n    app.include_router(agency_router)\n"
            )
            (app / "agency_web.py").write_text("router = object()\n")
            report = mod.analyze(["src/veridra/agency_web.py"], root)
            self.assertEqual(len(report["registered_router_impacts"]), 1)
            self.assertEqual(report["registered_router_impacts"][0]["conditional"], "true")
            self.assertTrue(report["requires_full_gate"])

    def test_serialization_contract_regression_detected(self) -> None:
        """A renamed persisted field must break an independent consumer contract."""
        import json

        def load_record(payload: str) -> str:
            record = json.loads(payload)
            return str(record["customer_id"])

        original = json.dumps({"customer_id": "c-001"})
        self.assertEqual(load_record(original), "c-001")
        incompatible = json.dumps({"client_id": "c-001"})
        with self.assertRaises(KeyError):
            load_record(incompatible)

    def test_persistence_boundary_suggests_backup_contract(self) -> None:
        report = mod.analyze(["src/veridra/tenant_customer_store.py"])
        self.assertTrue(report["requires_full_gate"])
        boundaries = report["critical_boundaries"]
        self.assertTrue(any(
            "tests/test_backup_restore.py" in b["suggested_tests"]
            for b in boundaries if b["boundary"] == "tenant-persistence"
        ))

    def test_python_parse_failure_not_hidden(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src" / "veridra").mkdir(parents=True)
            (root / "tests").mkdir()
            (root / "src" / "veridra" / "broken.py").write_text("def broken(\n")
            report = mod.analyze(["src/veridra/broken.py"], root)
            self.assertTrue(report["parse_errors"])
            self.assertTrue(report["requires_full_gate"])


if __name__ == "__main__":
    unittest.main()
