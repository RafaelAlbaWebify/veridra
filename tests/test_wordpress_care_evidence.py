import json
import tempfile
import unittest
from pathlib import Path
from tools.wordpress_care_evidence import collect

class EvidenceIndexTests(unittest.TestCase):
    def test_three_known_contracts(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root) / "acceptance"
            samples = [
                ("care-maintenance", {"contract":"webify_wordpress_care_lab_v1", "passed":True, "checks":{"http_200":"PASS"}}),
                ("care-restore", {"contract":"wordpress_care_isolated_restore_v1", "passed":True, "checks":{"restored_content":"PASS"}}),
                ("care-cycle", {"contract":"webify_wordpress_care_cycle_v1", "passed":True, "steps":{"inspect":"PASS","backup":"PASS"}}),
            ]
            for folder, obj in samples:
                dest = base / folder
                dest.mkdir(parents=True)
                (dest / "sample.json").write_text(json.dumps(obj))
            result = collect(Path(root))
            self.assertEqual(result["counts"], {"PASS":3, "FAIL":0, "INVALID":0})

    def test_rejects_fake_success(self):
        with tempfile.TemporaryDirectory() as root:
            dest = Path(root) / "acceptance" / "care-cycle"
            dest.mkdir(parents=True)
            (dest / "fake.json").write_text(json.dumps({"contract":"webify_wordpress_care_cycle_v1","passed":True,"steps":{"backup":"FAIL"}}))
            self.assertEqual(collect(Path(root))["counts"]["FAIL"],1)

    def test_rejects_unknown_contract(self):
        with tempfile.TemporaryDirectory() as root:
            dest = Path(root) / "acceptance" / "care-cycle"
            dest.mkdir(parents=True)
            (dest / "unknown.json").write_text(json.dumps({"contract":"unknown","passed":True,"steps":{"backup":"PASS"}}))
            self.assertEqual(collect(Path(root))["counts"]["INVALID"],1)

if __name__ == "__main__":
    unittest.main()
