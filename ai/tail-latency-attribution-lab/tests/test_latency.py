import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from latency import TraceError, analyze


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = json.loads((ROOT / "samples" / "shopping.json").read_text(encoding="utf-8"))


class LatencyTests(unittest.TestCase):
    def test_p95_and_exclusive_candidate(self):
        result = analyze(SAMPLE)
        self.assertEqual(result["p95_root_latency_ms"], 240)
        self.assertEqual(result["slow_trace_candidates"][0]["service"], "catalog")
        self.assertEqual(result["slow_trace_candidates"][0]["exclusive_ms"], 200)

    def test_concurrent_children_are_not_double_counted(self):
        case = copy.deepcopy(SAMPLE)
        case["traces"][1]["spans"].append({"id": "search", "service": "search", "parent": "catalog", "start_ms": 20, "duration_ms": 20})
        self.assertEqual(analyze(case)["slow_trace_candidates"][0]["exclusive_ms"], 190)

    def test_reordering_preserves_digest(self):
        case = copy.deepcopy(SAMPLE)
        case["traces"].reverse()
        for trace in case["traces"]:
            trace["spans"].reverse()
        self.assertEqual(analyze(case)["evidence_sha256"], analyze(SAMPLE)["evidence_sha256"])

    def test_changed_duration_changes_digest(self):
        case = copy.deepcopy(SAMPLE)
        case["traces"][0]["spans"][0]["duration_ms"] += 1
        self.assertNotEqual(analyze(case)["evidence_sha256"], analyze(SAMPLE)["evidence_sha256"])

    def test_rejects_orphan_cycle_and_outside_interval(self):
        for mutation in ("orphan", "cycle", "outside"):
            case = copy.deepcopy(SAMPLE)
            spans = case["traces"][0]["spans"]
            if mutation == "orphan":
                spans[1]["parent"] = "missing"
            elif mutation == "cycle":
                spans[0]["parent"] = "cache"
            else:
                spans[2]["duration_ms"] = 100
            with self.subTest(mutation=mutation), self.assertRaises(TraceError):
                analyze(case)

    def test_rejects_boolean_duration_and_duplicate(self):
        case = copy.deepcopy(SAMPLE)
        case["traces"][0]["spans"][1]["duration_ms"] = True
        with self.assertRaises(TraceError):
            analyze(case)
        case = copy.deepcopy(SAMPLE)
        case["traces"][1]["id"] = "request-1"
        with self.assertRaises(TraceError):
            analyze(case)

    def test_cli_success_and_reject(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "traces.json"
            source.write_text(json.dumps(SAMPLE), encoding="utf-8")
            good = subprocess.run([sys.executable, "-B", str(ROOT / "latency.py"), str(source)], capture_output=True, text=True)
            self.assertEqual(good.returncode, 0, good.stderr)
            source.write_text("{}", encoding="utf-8")
            bad = subprocess.run([sys.executable, "-B", str(ROOT / "latency.py"), str(source)], capture_output=True, text=True)
            self.assertEqual(bad.returncode, 2)


if __name__ == "__main__":
    unittest.main()
