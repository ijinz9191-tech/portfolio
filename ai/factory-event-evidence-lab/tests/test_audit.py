import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from audit import AuditError, audit  # noqa: E402


def sample():
    return json.loads((ROOT / "samples" / "events.json").read_text(encoding="utf-8"))


class AuditTests(unittest.TestCase):
    def test_complete_sequence(self):
        result = audit(sample())
        self.assertEqual(result["lots"][0]["decision"], "COMPLETE")

    def test_incomplete_sequence_is_gap(self):
        data = sample()
        data["events"].pop()
        self.assertEqual(audit(data)["lots"][0]["decision"], "EVIDENCE_GAP")

    def test_missing_handoff_is_rejected(self):
        data = sample()
        del data["events"][2]
        with self.assertRaises(AuditError):
            audit(data)

    def test_duplicate_id_is_rejected(self):
        data = sample()
        data["events"][1]["id"] = "e-01"
        with self.assertRaises(AuditError):
            audit(data)

    def test_ambiguous_time_is_rejected(self):
        data = sample()
        data["events"][1]["at"] = "2026-09-29T09:01:00"
        with self.assertRaises(AuditError):
            audit(data)

    def test_unordered_source_has_same_evidence(self):
        data = sample()
        shuffled = copy.deepcopy(data)
        shuffled["events"].reverse()
        self.assertEqual(audit(data)["evidence_sha256"], audit(shuffled)["evidence_sha256"])

    def test_cli(self):
        completed = subprocess.run([sys.executable, str(ROOT / "audit.py"),
                                    str(ROOT / "samples" / "events.json")],
                                   capture_output=True, text=True, encoding="utf-8", check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["decision"], "EVENT_SEQUENCE_AUDITED")


if __name__ == "__main__":
    unittest.main()
