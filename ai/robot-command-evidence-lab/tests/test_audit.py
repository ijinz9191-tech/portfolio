import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path

from audit import AuditError, audit


SAMPLE = json.loads((Path(__file__).resolve().parents[1] / "samples" / "commands.json").read_text(encoding="utf-8"))


class RobotCommandTests(unittest.TestCase):
    def test_complete_and_missing_evidence(self):
        result = audit(SAMPLE)
        self.assertEqual([row["decision"] for row in result["commands"]], ["SUCCEEDED", "EVIDENCE_GAP"])

    def test_duplicate_request_rejected(self):
        doc = copy.deepcopy(SAMPLE)
        doc["commands"][1]["request_id"] = "r-001"
        with self.assertRaisesRegex(AuditError, "duplicate"):
            audit(doc)

    def test_time_reversal_rejected(self):
        doc = copy.deepcopy(SAMPLE)
        doc["commands"][0]["completed_at"] = "2026-09-29T09:00:00Z"
        with self.assertRaisesRegex(AuditError, "completion"):
            audit(doc)

    def test_completion_without_acceptance_rejected(self):
        doc = copy.deepcopy(SAMPLE)
        doc["commands"][0]["accepted_at"] = None
        with self.assertRaisesRegex(AuditError, "completion"):
            audit(doc)

    def test_observed_result_requires_timestamp(self):
        doc = copy.deepcopy(SAMPLE)
        doc["commands"][1]["result"] = "SUCCEEDED"
        with self.assertRaisesRegex(AuditError, "agree"):
            audit(doc)

    def test_overlapping_commands_rejected(self):
        doc = copy.deepcopy(SAMPLE)
        doc["commands"][1]["requested_at"] = "2026-09-29T09:00:08Z"
        with self.assertRaisesRegex(AuditError, "overlapping"):
            audit(doc)

    def test_failed_command_and_deterministic_hash(self):
        doc = copy.deepcopy(SAMPLE)
        doc["commands"][1]["completed_at"] = "2026-09-29T09:00:12Z"
        doc["commands"][1]["result"] = "FAILED"
        result = audit(doc)
        self.assertEqual(result["commands"][1]["decision"], "FAILED")
        doc["commands"].reverse()
        self.assertEqual(result["evidence_sha256"], audit(doc)["evidence_sha256"])

    def test_cli(self):
        child = subprocess.run([sys.executable, "-B", "audit.py", "samples/commands.json"],
                               text=True, capture_output=True)
        self.assertEqual(child.returncode, 0, child.stderr)
        self.assertEqual(json.loads(child.stdout)["commands"][1]["decision"], "EVIDENCE_GAP")


if __name__ == "__main__":
    unittest.main()
