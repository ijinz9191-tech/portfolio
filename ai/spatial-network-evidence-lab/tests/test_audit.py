import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from audit import SpatialError, audit


ROOT = Path(__file__).resolve().parents[1]
CASE = json.loads((ROOT / "samples" / "network.json").read_text(encoding="utf-8"))


class SpatialAuditTests(unittest.TestCase):
    def test_valid_route_reports_distance_and_hash(self):
        result = audit(CASE)
        self.assertEqual(result["decision"], "TOPOLOGY_VERIFIED")
        self.assertEqual(result["routes"][0]["distance_m"], 210)
        self.assertEqual(result["routes"][0]["start"], "hub")

    def test_order_independent_evidence_hash(self):
        shuffled = copy.deepcopy(CASE)
        shuffled["nodes"].reverse()
        shuffled["edges"].reverse()
        self.assertEqual(audit(shuffled)["evidence_sha256"], audit(CASE)["evidence_sha256"])

    def test_rejects_dangling_edge(self):
        case = copy.deepcopy(CASE)
        case["edges"][0]["to"] = "missing"
        with self.assertRaisesRegex(SpatialError, "dangling"):
            audit(case)

    def test_rejects_disconnected_route(self):
        case = copy.deepcopy(CASE)
        case["routes"][0]["edge_ids"] = ["b", "a"]
        with self.assertRaisesRegex(SpatialError, "disconnected"):
            audit(case)

    def test_rejects_impossible_distance(self):
        case = copy.deepcopy(CASE)
        case["edges"][0]["distance_m"] = 1
        with self.assertRaisesRegex(SpatialError, "shorter"):
            audit(case)

    def test_rejects_bad_coordinate_and_duplicate(self):
        case = copy.deepcopy(CASE)
        case["nodes"][0]["lat"] = 100
        with self.assertRaisesRegex(SpatialError, "latitude"):
            audit(case)
        case = copy.deepcopy(CASE)
        case["nodes"][1]["id"] = case["nodes"][0]["id"]
        with self.assertRaisesRegex(SpatialError, "duplicate"):
            audit(case)

    def test_cli_success_and_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "input.json"
            file.write_text(json.dumps(CASE), encoding="utf-8")
            good = subprocess.run([sys.executable, "-B", str(ROOT / "audit.py"), str(file)], capture_output=True, text=True)
            self.assertEqual(good.returncode, 0, good.stderr)
            self.assertEqual(json.loads(good.stdout)["decision"], "TOPOLOGY_VERIFIED")
            file.write_text("{}", encoding="utf-8")
            bad = subprocess.run([sys.executable, "-B", str(ROOT / "audit.py"), str(file)], capture_output=True, text=True)
            self.assertEqual(bad.returncode, 2)


if __name__ == "__main__":
    unittest.main()
