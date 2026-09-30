import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audit import InputError, audit

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = json.loads((ROOT / "samples" / "expand-migrate.json").read_text(encoding="utf-8"))


class RolloutTests(unittest.TestCase):
    def test_expand_and_mixed_fleet_pass(self):
        result = audit(SAMPLE)
        self.assertEqual(result["decision"], "PASS")
        self.assertEqual(result["stages_checked"], 3)
        self.assertEqual(result["findings"], [])

    def test_contract_breaks_rollback_even_after_old_nodes_leave(self):
        payload = copy.deepcopy(SAMPLE)
        payload["schemas"]["v3"]["columns"].remove("status")
        payload["schemas"]["v3"]["required_on_insert"].remove("status")
        result = audit(payload)
        self.assertEqual(result["decision"], "REVIEW_REQUIRED")
        self.assertTrue(any(item["rollback_only"] and item["issue"] == "MISSING_READ_COLUMN"
                            for item in result["findings"]))

    def test_required_new_column_without_default_breaks_old_writer(self):
        payload = copy.deepcopy(SAMPLE)
        payload["schemas"]["v2"]["defaults"] = []
        result = audit(payload)
        self.assertTrue(any(item["app"] == "old" and item["issue"] == "REQUIRED_INSERT_COLUMN"
                            for item in result["findings"]))

    def test_new_app_before_schema_expansion_is_rejected(self):
        payload = copy.deepcopy(SAMPLE)
        payload["stages"][0]["running_apps"].append("new")
        self.assertTrue(any(item["issue"] == "MISSING_READ_COLUMN" for item in audit(payload)["findings"]))

    def test_duplicate_stage_and_unknown_version_rejected(self):
        payload = copy.deepcopy(SAMPLE)
        payload["stages"][1]["name"] = "기존"
        with self.assertRaises(InputError):
            audit(payload)
        payload = copy.deepcopy(SAMPLE)
        payload["stages"][0]["schema"] = "missing"
        with self.assertRaises(InputError):
            audit(payload)

    def test_hash_is_stable_under_json_key_order(self):
        a = audit(SAMPLE)
        b = audit(json.loads(json.dumps(SAMPLE, sort_keys=True)))
        self.assertEqual(a["evidence_sha256"], b["evidence_sha256"])

    def test_cli_and_failure_exit_codes(self):
        good = subprocess.run([sys.executable, "-B", str(ROOT / "audit.py"), str(ROOT / "samples" / "expand-migrate.json")],
                              text=True, capture_output=True)
        self.assertEqual(good.returncode, 0, good.stderr)
        self.assertEqual(json.loads(good.stdout)["decision"], "PASS")
        bad = subprocess.run([sys.executable, "-B", str(ROOT / "audit.py"), str(ROOT / "missing.json")],
                             text=True, capture_output=True)
        self.assertEqual(bad.returncode, 2)


if __name__ == "__main__":
    unittest.main()
