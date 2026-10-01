import copy
import random
import unittest

from latency import TraceError, _union_ms, analyze


class IndexedSpanTests(unittest.TestCase):
    def test_interval_union_matches_integer_timeline_oracle(self):
        generator = random.Random(401)
        for _ in range(100):
            intervals = [
                (generator.randrange(50), generator.randrange(51, 100))
                for _ in range(12)
            ]
            covered = {
                instant for start, end in intervals for instant in range(start, end)
            }
            self.assertEqual(_union_ms(intervals), len(covered))

    def test_deep_tree_and_disconnected_cycle_reject_without_recursion(self):
        spans = [
            {
                "id": f"s{i}",
                "service": "synthetic",
                "parent": f"s{i - 1}" if i else None,
                "start_ms": 0,
                "duration_ms": 100,
            }
            for i in range(1500)
        ]
        document = {
            "scenario": "deep",
            "traces": [
                {"id": "a", "spans": spans},
                {"id": "b", "spans": copy.deepcopy(spans)},
            ],
        }
        result = analyze(document)
        self.assertEqual(result["sample_count"], 2)
        self.assertEqual(
            result["slow_trace_candidates"][0]["largest_exclusive_span"], "s1499"
        )
        spans[1]["parent"] = "s2"
        with self.assertRaisesRegex(TraceError, "cycle"):
            analyze(document)
