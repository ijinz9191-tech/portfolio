import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from audit import ContractError, analyze


ROOT = Path(__file__).resolve().parents[1]


def fixture():
    return json.loads((ROOT / "samples" / "change.json").read_text(encoding="utf-8"))


class ContractTests(unittest.TestCase):
    def test_additive_change_passes(self):
        result = analyze(fixture())
        self.assertEqual(result["decision"], "PASS")
        self.assertEqual(result["consumer_impacts"], [])

    def test_missing_field_blocks_without_acknowledgement(self):
        item = fixture()
        item["after"][0]["fields"].remove("state")
        result = analyze(item)
        self.assertEqual(result["decision"], "BLOCK")
        self.assertEqual(result["consumer_impacts"][0]["missing_fields"], ["state"])

    def test_removed_route_blocks_registered_consumer(self):
        item = fixture()
        item["after"] = []
        result = analyze(item)
        self.assertEqual(result["decision"], "BLOCK")
        self.assertTrue(result["consumer_impacts"][0]["route_removed"])

    def test_acknowledged_breakage_still_needs_review(self):
        item = fixture()
        item["after"][0]["fields"].remove("state")
        item["consumers"][0]["acknowledged"] = True
        self.assertEqual(analyze(item)["decision"], "REVIEW")
        item["rollback_plan"] = ""
        self.assertEqual(analyze(item)["decision"], "BLOCK")

    def test_security_downgrade_always_blocks(self):
        item = fixture()
        item["after"][0]["auth"] = "public"
        result = analyze(item)
        self.assertEqual(result["decision"], "BLOCK")
        self.assertEqual(result["security_downgrades"], ["GET /orders"])

    def test_uncovered_removed_route_needs_review(self):
        item = fixture()
        item["before"].append({"route": "GET /legacy", "auth": "authenticated", "fields": ["id"]})
        self.assertEqual(analyze(item)["decision"], "REVIEW")
        self.assertEqual(analyze(item)["uncovered_breaking_routes"], ["GET /legacy"])

    def test_invalid_baseline_or_duplicate_rejects(self):
        item = fixture()
        item["consumers"][0]["fields"].append("missing")
        with self.assertRaises(ContractError):
            analyze(item)
        item = fixture()
        item["after"][0]["auth"] = []
        with self.assertRaises(ContractError):
            analyze(item)
        item = fixture()
        item["after"].append(copy.deepcopy(item["after"][0]))
        with self.assertRaises(ContractError):
            analyze(item)

    def test_order_independent_hash(self):
        item = fixture()
        item["before"][0]["fields"].reverse()
        item["after"][0]["fields"].reverse()
        self.assertEqual(analyze(item)["evidence_sha256"], analyze(fixture())["evidence_sha256"])

    def test_cli_success_and_reject(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "change.json"
            source.write_text(json.dumps(fixture()), encoding="utf-8")
            ok = subprocess.run([sys.executable, "-B", str(ROOT / "audit.py"), str(source)],
                                capture_output=True, text=True)
            self.assertEqual(ok.returncode, 0, ok.stderr)
            self.assertEqual(json.loads(ok.stdout)["decision"], "PASS")
            source.write_text("{}", encoding="utf-8")
            bad = subprocess.run([sys.executable, "-B", str(ROOT / "audit.py"), str(source)],
                                 capture_output=True, text=True)
            self.assertEqual(bad.returncode, 2)


if __name__ == "__main__":
    unittest.main()
