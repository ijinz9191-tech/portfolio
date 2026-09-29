import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from triage import TriageError, analyze


ROOT = Path(__file__).resolve().parents[1]


def snapshot():
    return {"incident_id": "synthetic-incident-42", "services": [
        {"id": "api", "depends_on": ["auth", "database"], "healthy": False, "evidence": "5xx probe"},
        {"id": "database", "depends_on": [], "healthy": False, "evidence": "connection probe"},
        {"id": "auth", "depends_on": [], "healthy": True, "evidence": "login probe"},
        {"id": "checkout", "depends_on": ["api"], "healthy": False, "evidence": "checkout probe"},
    ]}


class TriageTests(unittest.TestCase):
    def test_dependency_first_candidates_and_impact(self):
        result = analyze(snapshot())
        self.assertEqual(result["first_failed_candidates"], ["database"])
        self.assertEqual(result["dependency_first_review_order"], ["database", "api", "checkout"])
        self.assertEqual(result["potentially_affected_by_candidate"]["database"], ["api", "checkout"])

    def test_order_does_not_change_hash(self):
        reordered = snapshot()
        reordered["services"].reverse()
        self.assertEqual(analyze(snapshot())["evidence_sha256"], analyze(reordered)["evidence_sha256"])

    def test_changed_evidence_changes_hash(self):
        changed = snapshot()
        changed["services"][0]["evidence"] = "another probe"
        self.assertNotEqual(analyze(snapshot())["evidence_sha256"], analyze(changed)["evidence_sha256"])

    def test_healthy_downstream_is_counterevidence(self):
        changed = snapshot()
        changed["services"][0]["healthy"] = True
        result = analyze(changed)
        self.assertIn("api", result["healthy_downstream_counterevidence"])
        self.assertNotIn("api", result["observed_failed"])

    def test_no_failure_does_not_invent_cause(self):
        changed = snapshot()
        for service in changed["services"]:
            service["healthy"] = True
        self.assertEqual(analyze(changed)["decision"], "NO_OBSERVED_FAILURE")
        self.assertEqual(analyze(changed)["first_failed_candidates"], [])

    def test_unknown_and_cycle_reject(self):
        unknown = snapshot()
        unknown["services"][0]["depends_on"].append("missing")
        with self.assertRaisesRegex(TriageError, "unknown"):
            analyze(unknown)
        cycle = snapshot()
        cycle["services"][1]["depends_on"] = ["api"]
        with self.assertRaisesRegex(TriageError, "cycle"):
            analyze(cycle)

    def test_missing_evidence_and_duplicate_reject(self):
        missing = snapshot()
        missing["services"][0]["evidence"] = ""
        with self.assertRaisesRegex(TriageError, "evidence"):
            analyze(missing)
        duplicate = snapshot()
        duplicate["services"][1]["id"] = "api"
        with self.assertRaisesRegex(TriageError, "unique"):
            analyze(duplicate)

    def test_cli_success_and_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "case.json"
            source.write_text(json.dumps(snapshot()), encoding="utf-8")
            ok = subprocess.run([sys.executable, "-B", str(ROOT / "triage.py"), str(source)],
                                capture_output=True, text=True)
            self.assertEqual(ok.returncode, 0, ok.stderr)
            self.assertEqual(json.loads(ok.stdout)["first_failed_candidates"], ["database"])
            source.write_text("{}", encoding="utf-8")
            bad = subprocess.run([sys.executable, "-B", str(ROOT / "triage.py"), str(source)],
                                 capture_output=True, text=True)
            self.assertEqual(bad.returncode, 2)
            self.assertIn("REJECTED", bad.stderr)


if __name__ == "__main__":
    unittest.main()
