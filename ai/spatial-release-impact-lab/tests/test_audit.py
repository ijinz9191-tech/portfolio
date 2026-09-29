import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from audit import ReleaseError, audit


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = json.loads((ROOT / "samples" / "change.json").read_text(encoding="utf-8"))


class ReleaseImpactTests(unittest.TestCase):
    def test_only_changed_route_needs_acknowledgement(self):
        result = audit(SAMPLE)
        self.assertEqual(result["decision"], "READY_FOR_HUMAN_REVIEW")
        self.assertEqual(result["changed_segments"], ["분기-광장"])
        self.assertEqual(result["impacted_routes"], ["광장행"])

    def test_missing_acknowledgement_blocks_release(self):
        case = copy.deepcopy(SAMPLE)
        case["acknowledgements"] = []
        result = audit(case)
        self.assertEqual(result["decision"], "BLOCKED")
        self.assertEqual(result["missing_acknowledgements"], ["광장행"])

    def test_common_segment_change_impacts_both_routes(self):
        case = copy.deepcopy(SAMPLE)
        case["candidate"]["segments"][0]["geometry_revision"] = "좌표-a2"
        result = audit(case)
        self.assertEqual(result["impacted_routes"], ["공원행", "광장행"])
        self.assertEqual(result["missing_acknowledgements"], ["공원행"])

    def test_removed_segment_with_updated_route_still_requires_review(self):
        case = copy.deepcopy(SAMPLE)
        case["candidate"]["segments"] = [row for row in case["candidate"]["segments"] if row["id"] != "분기-광장"]
        case["candidate"]["routes"][0]["segment_ids"] = ["판교역-분기", "분기-공원"]
        self.assertIn("광장행", audit(case)["impacted_routes"])

    def test_route_reorder_is_a_change_even_with_same_segments(self):
        case = copy.deepcopy(SAMPLE)
        case["candidate"]["segments"][1]["geometry_revision"] = "좌표-b1"
        case["candidate"]["routes"][0]["segment_ids"].reverse()
        self.assertEqual(audit(case)["impacted_routes"], ["광장행"])

    def test_new_route_needs_a_review(self):
        case = copy.deepcopy(SAMPLE)
        case["candidate"]["routes"].append({"id": "신규경로", "segment_ids": ["분기-공원"]})
        result = audit(case)
        self.assertEqual(result["decision"], "BLOCKED")
        self.assertEqual(result["missing_acknowledgements"], ["신규경로"])

    def test_unknown_segment_and_route_retirement_are_rejected(self):
        case = copy.deepcopy(SAMPLE)
        case["candidate"]["routes"][0]["segment_ids"].append("없는구간")
        with self.assertRaisesRegex(ReleaseError, "unknown segment"):
            audit(case)
        case = copy.deepcopy(SAMPLE)
        case["candidate"]["routes"].pop()
        with self.assertRaisesRegex(ReleaseError, "retirement"):
            audit(case)

    def test_wrong_rollback_and_extra_acknowledgement_are_rejected(self):
        case = copy.deepcopy(SAMPLE)
        case["acknowledgements"][0]["rollback_version"] = "지도-v0"
        with self.assertRaisesRegex(ReleaseError, "rollback"):
            audit(case)
        case = copy.deepcopy(SAMPLE)
        case["acknowledgements"].append({"route_id": "공원행", "reviewer": "가상 담당자", "rollback_version": "지도-v1"})
        with self.assertRaisesRegex(ReleaseError, "unexpected"):
            audit(case)

    def test_input_order_does_not_change_evidence_hash(self):
        case = copy.deepcopy(SAMPLE)
        for label in ("baseline", "candidate"):
            case[label]["segments"].reverse()
            case[label]["routes"].reverse()
        self.assertEqual(audit(case)["evidence_sha256"], audit(SAMPLE)["evidence_sha256"])

    def test_cli_exit_codes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "change.json"
            path.write_text(json.dumps(SAMPLE, ensure_ascii=False), encoding="utf-8")
            good = subprocess.run([sys.executable, "-B", str(ROOT / "audit.py"), str(path)], capture_output=True, text=True)
            self.assertEqual(good.returncode, 0, good.stderr)
            case = copy.deepcopy(SAMPLE)
            case["acknowledgements"] = []
            path.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
            blocked = subprocess.run([sys.executable, "-B", str(ROOT / "audit.py"), str(path)], capture_output=True, text=True)
            self.assertEqual(blocked.returncode, 1)
            path.write_text("{}", encoding="utf-8")
            invalid = subprocess.run([sys.executable, "-B", str(ROOT / "audit.py"), str(path)], capture_output=True, text=True)
            self.assertEqual(invalid.returncode, 2)


if __name__ == "__main__":
    unittest.main()
