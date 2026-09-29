import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from audit import AuditError, audit

ROOT = Path(__file__).resolve().parents[1]
CASE = json.loads((ROOT / "samples" / "routes.json").read_text(encoding="utf-8"))


class AuditTests(unittest.TestCase):
    def test_on_time_and_overdue(self):
        result = audit(CASE)
        self.assertEqual([x["decision"] for x in result["deliveries"]], ["ON_TIME", "OVERDUE_OPEN"])

    def test_missing_handoff_is_unknown_outcome(self):
        case = copy.deepcopy(CASE)
        case["deliveries"][0]["events"].pop(2)
        result = audit(case)["deliveries"][0]
        self.assertEqual(result["decision"], "EVIDENCE_GAP")
        self.assertEqual(result["missing_handoffs"], ["picked_up"])

    def test_late_completion_and_boundary(self):
        case = copy.deepcopy(CASE)
        case["deliveries"][0]["events"][-1]["at_min"] = 91
        self.assertEqual(audit(case)["deliveries"][0]["decision"], "LATE_COMPLETION")
        case["deliveries"][0]["events"][-1]["at_min"] = 90
        self.assertEqual(audit(case)["deliveries"][0]["decision"], "ON_TIME")

    def test_order_independent_digest(self):
        case = copy.deepcopy(CASE)
        case["deliveries"].reverse()
        self.assertEqual(audit(case)["evidence_sha256"], audit(CASE)["evidence_sha256"])

    def test_rejects_bad_times_stages_and_actor(self):
        for mutation in ("future", "duplicate", "actor", "order", "bool"):
            case = copy.deepcopy(CASE)
            row = case["deliveries"][0]["events"]
            if mutation == "future": row[-1]["at_min"] = 121
            if mutation == "duplicate": row[-1]["stage"] = "picked_up"
            if mutation == "actor": row[1]["actor"] = ""
            if mutation == "order": row[1]["at_min"] = 0
            if mutation == "bool": row[1]["at_min"] = True
            with self.subTest(mutation=mutation), self.assertRaises(AuditError): audit(case)

    def test_cli_success_and_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "input.json"
            file.write_text(json.dumps(CASE), encoding="utf-8")
            good = subprocess.run([sys.executable, "-B", str(ROOT / "audit.py"), str(file)], capture_output=True, text=True)
            self.assertEqual(good.returncode, 0, good.stderr)
            file.write_text("{}", encoding="utf-8")
            bad = subprocess.run([sys.executable, "-B", str(ROOT / "audit.py"), str(file)], capture_output=True, text=True)
            self.assertEqual(bad.returncode, 2)


if __name__ == "__main__": unittest.main()
