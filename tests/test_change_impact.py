"""Contract tests for the static change-impact tool; no live customer data."""
import importlib.util
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

    def test_unmodelled_change_forces_full_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src" / "veridra").mkdir(parents=True)
            (root / "tests").mkdir()
            report = mod.analyze([".github/workflows/ci.yml"], root)
            self.assertTrue(report["requires_full_gate"])
            self.assertEqual(report["unmodelled_changed_files"], [".github/workflows/ci.yml"])

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
