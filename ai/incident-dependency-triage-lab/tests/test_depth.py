import random
import unittest

from triage import TriageError, analyze


class GraphDepthTests(unittest.TestCase):
    def test_deep_chain_and_deep_cycle_do_not_use_python_recursion(self):
        count = 1500
        rows = [
            {
                "id": f"s{i:04}",
                "depends_on": [f"s{i - 1:04}"] if i else [],
                "healthy": False,
                "evidence": "synthetic",
            }
            for i in range(count)
        ]
        document = {"incident_id": "deep", "services": rows}
        result = analyze(document)
        self.assertEqual(result["first_failed_candidates"], ["s0000"])
        self.assertEqual(
            len(result["potentially_affected_by_candidate"]["s0000"]), count - 1
        )
        rows[0]["depends_on"] = [f"s{count - 1:04}"]
        with self.assertRaisesRegex(TriageError, "cycle"):
            analyze(document)

    def test_reverse_reachability_matches_transitive_closure_oracle(self):
        randomizer = random.Random(942)
        rows = [
            {
                "id": f"s{i:02}",
                "depends_on": [
                    f"s{j:02}" for j in range(i) if randomizer.random() < 0.18
                ],
                "healthy": i % 3 == 0,
                "evidence": "synthetic",
            }
            for i in range(40)
        ]
        result = analyze({"incident_id": "oracle", "services": rows})
        for root, actual in result["potentially_affected_by_candidate"].items():
            reached = {root}
            while True:
                before = set(reached)
                reached.update(
                    row["id"] for row in rows if set(row["depends_on"]) & reached
                )
                if reached == before:
                    break
            self.assertEqual(actual, sorted(reached - {root}))
